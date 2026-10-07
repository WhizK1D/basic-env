#!/usr/bin/env python3
"""Regression tests for the basic-env installer stages and orchestrator.

Everything runs against temporary HOME directories. apt/sudo/git-clone/curl
are PATH stubs; no real package, download, or clone operations happen.
"""

import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ORCH = REPO / "setup_environment.sh"
BASH = "/bin/bash"

# Real utilities the stage scripts need (kept on PATH via symlinks).
REAL_TOOLS = ["mkdir", "cp", "mv", "chmod", "date", "mktemp", "awk",
              "grep", "cmp", "cat", "rm", "ls", "basename"]

GIT_STUB = """\
#!/bin/sh
printf 'git' >> "$STUB_LOG"
printf '|%s' "$@" >> "$STUB_LOG"
printf '\\n' >> "$STUB_LOG"
case "$1" in
  clone)
    shift; for last in "$@"; do :; done
    mkdir -p "$last/.git" "$last/doc"; exit 0 ;;
  -C)
    case "$3" in
      rev-parse)
        case "$4" in
          --git-dir) [ -d "$2/.git" ] && { printf '.git\\n'; exit 0; } ; exit 128 ;;
          --show-toplevel)
            if [ -e "$2/.git" ]; then printf '%s\\n' "$2"; exit 0; fi
            exec /usr/bin/git "$@" ;;
        esac ;;
      checkout) exit 0 ;;
    esac ;;
  config) exec /usr/bin/git "$@" ;;
esac
exit 0
"""

CURL_STUB = """\
#!/bin/sh
printf 'curl|%s\\n' "$*" >> "$STUB_LOG"
[ -n "${FAIL_CURL:-}" ] && exit 1
prev=
for a in "$@"; do
  [ "$prev" = "-o" ] && printf 'stub-pathogen\\n' > "$a"
  prev=$a
done
exit 0
"""

SUDO_STUB = """\
#!/bin/sh
printf 'sudo' >> "$STUB_LOG"
printf '|%s' "$@" >> "$STUB_LOG"
printf '\\n' >> "$STUB_LOG"
exec "$@"
"""

APT_GET_STUB = """\
#!/bin/sh
printf 'apt-get|%s\\n' "$*" >> "$STUB_LOG"
exit 0
"""

APT_CACHE_STUB = """\
#!/bin/sh
if [ "$1" = "policy" ]; then
  case " ${APT_MISSING:-} " in *" $2 "*) printf 'Candidate: (none)\\n'; exit 0;; esac
  printf 'Candidate: 1.0\\n'; exit 0
fi
exit 0
"""

LOG_STUB = '#!/bin/sh\nprintf \'%s|%s\\n\' "$(basename "$0")" "$*" >> "$STUB_LOG"\nexit 0\n'

CTAGS_STUB = """\
#!/bin/sh
printf 'ctags|%s\\n' "$*" >> "$STUB_LOG"
[ "$1" = "--version" ] && printf '%s\\n' "${CTAGS_VERSION:-Universal Ctags 6.1.1}"
exit 0
"""


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="basic-env-inst-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.realbin = self.tmp / "realbin"
        self.realbin.mkdir()
        self.fakebin = self.tmp / "fakebin"
        self.fakebin.mkdir()
        self.logfile = self.tmp / "calls.log"
        for t in REAL_TOOLS:
            src = shutil.which(t)
            if src:
                (self.realbin / t).symlink_to(src)

    def stub(self, name, body=LOG_STUB):
        p = self.fakebin / name
        p.write_text(body)
        p.chmod(0o755)

    def env(self, **extra):
        e = {
            "PATH": f"{self.fakebin}:{self.realbin}",
            "STUB_LOG": str(self.logfile),
            "HOME": str(self.home),
            "TERM": "xterm",
        }
        e.update(extra)
        return e

    def orch(self, *args, **extra_env):
        return subprocess.run(
            [str(ORCH), *args], capture_output=True, text=True,
            env=self.env(**extra_env), timeout=60,
        )

    def calls(self):
        if not self.logfile.exists():
            return []
        return self.logfile.read_text().splitlines()

    def install_stubs(self, present=()):
        """Stubs for install stage: mocked network/pkg tools plus
        'present' binaries so they are skipped by the apt check."""
        self.stub("git", GIT_STUB)
        self.stub("curl", CURL_STUB)
        self.stub("sudo", SUDO_STUB)
        self.stub("apt-get", APT_GET_STUB)
        self.stub("apt-cache", APT_CACHE_STUB)
        for t in present:
            if t == "ctags":
                self.stub(t, CTAGS_STUB)
            elif not (self.fakebin / t).exists():
                self.stub(t)


class TestOrchestrator(Fixture):
    def test_no_args_prints_help_no_side_effects(self):
        r = self.orch()
        self.assertEqual(r.returncode, 0)
        self.assertIn("Usage:", r.stdout)
        self.assertEqual(list(self.home.iterdir()), [])

    def test_unknown_stage_and_option_fail(self):
        for arg in ("bogus", "--bogus"):
            r = self.orch(arg)
            self.assertEqual(r.returncode, 2, arg)
            self.assertIn("unknown argument", r.stderr)

    def test_stage_help(self):
        for s in ("install-tools.sh", "setup-shell.sh", "configure-tools.sh"):
            r = subprocess.run(
                [str(REPO / "scripts" / s), "--help"],
                capture_output=True, text=True, env=self.env(),
            )
            self.assertEqual(r.returncode, 0, s)
            self.assertIn("usage:", r.stdout)


class TestInstallStage(Fixture):
    def test_order_and_missing_packages(self):
        # git, curl, vim present; terminator, eza, bat, ctags missing.
        self.install_stubs(present=["git", "curl", "vim"])
        r = self.orch("install")
        self.assertEqual(r.returncode, 0, r.stderr)
        calls = self.calls()
        apt = next(c for c in calls
                   if "apt-get" in c and "install" in c)
        pkgs = set(apt.split("install", 1)[1].replace("|", " ").split())
        self.assertEqual(pkgs, {"terminator", "eza", "bat", "universal-ctags"})
        i_apt = calls.index(apt)
        i_curl = next(i for i, c in enumerate(calls) if c.startswith("curl|"))
        i_l9 = next(i for i, c in enumerate(calls)
                    if "clone|https://github.com/vim-scripts/L9.git" in c)
        self.assertTrue(i_apt < i_curl < i_l9, calls)
        self.assertTrue(any("checkout|c822b05ee0886f9a9703227dc85a6d47612c4bf1"
                            in c for c in calls))
        # every plugin cloned, helptags generated through stubbed vim
        clones = [c for c in calls if "|clone|" in c]
        self.assertEqual(len(clones), 22)
        self.assertTrue(any(c.startswith("vim|--noplugin")
                            for c in calls))

    def test_missing_apt_candidate_fails(self):
        self.install_stubs(present=["git", "curl", "vim"])
        r = self.orch("install", APT_MISSING="eza")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("no apt installation candidate for 'eza'", r.stderr)

    def test_pathogen_existing_preserved(self):
        p = self.home / ".vim/autoload/pathogen.vim"
        p.parent.mkdir(parents=True)
        p.write_text("SENTINEL")
        self.install_stubs(present=["git", "curl", "vim", "terminator",
                                    "eza", "batcat", "ctags"])
        r = self.orch("install")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(p.read_text(), "SENTINEL")
        self.assertFalse(any(c.startswith("curl|") for c in self.calls()))

    def test_existing_checkout_skipped_and_conflict_fails(self):
        existing = self.home / ".vim/bundle/ctrlp.vim/.git"
        existing.mkdir(parents=True)
        conflict = self.home / ".vim/bundle/supertab"
        conflict.mkdir(parents=True)
        self.install_stubs(present=["git", "curl", "vim", "terminator",
                                    "eza", "batcat", "ctags"])
        r = self.orch("install")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not a git checkout", r.stderr)
        # ctrlp was skipped (no clone call for it before the failure)
        self.assertFalse(any("ctrlp.vim" in c and "|clone|" in c
                             for c in self.calls()))

    def test_failed_download_aborts_before_configure(self):
        self.install_stubs(present=["git", "vim", "terminator", "eza",
                                    "batcat", "ctags"])
        r = self.orch("all", FAIL_CURL="1")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("Pathogen download failed", r.stderr)
        # shell/configure stages never ran
        self.assertFalse((self.home / ".env/.setup").exists())
        self.assertFalse((self.home / ".vimrc").exists())


class TestShellStage(Fixture):
    def test_modules_keys_and_block_idempotent(self):
        for _ in range(2):
            r = self.orch("shell")
            self.assertEqual(r.returncode, 0, r.stderr)
        for m in (".setup", ".colors", ".aliases", ".prompt"):
            self.assertTrue((self.home / ".env" / m).is_file(), m)
        keys = self.home / ".env/.keys"
        self.assertTrue(keys.is_file())
        self.assertEqual(stat.S_IMODE(keys.stat().st_mode), 0o600)
        bashrc = (self.home / ".bashrc").read_text()
        self.assertEqual(bashrc.count("# >>> basic-env >>>"), 1)
        self.assertEqual(bashrc.count("$HOME/.env/.setup"), 2)  # if+source lines

    def test_unmarked_hook_reused(self):
        hook = ('if [ -f "$HOME/.env/.setup" ]; then\n'
                '    . "$HOME/.env/.setup"\nfi\n')
        (self.home / ".bashrc").write_text("# preamble\n" + hook)
        r = self.orch("shell")
        self.assertEqual(r.returncode, 0, r.stderr)
        text = (self.home / ".bashrc").read_text()
        self.assertNotIn(">>> basic-env", text)
        self.assertEqual(text.count('. "$HOME/.env/.setup"'), 1)
        self.assertIn("# preamble", text)

    def test_preflight_conflict_no_partial_writes(self):
        envdir = self.home / ".env"
        envdir.mkdir()
        (envdir / ".aliases").write_text("mine\n")
        (self.home / ".bashrc").write_text("keepme\n")
        r = self.orch("shell")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("conflict", r.stderr)
        self.assertEqual((envdir / ".aliases").read_text(), "mine\n")
        self.assertFalse((envdir / ".colors").exists())     # nothing written
        self.assertEqual((self.home / ".bashrc").read_text(), "keepme\n")

    def test_replace_configs_backs_up(self):
        envdir = self.home / ".env"
        envdir.mkdir()
        target = envdir / ".aliases"
        target.write_text("old content\n")
        r = self.orch("shell", "--replace-configs")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("eza", target.read_text())
        backups = list((self.home / ".local/state/basic-env/backups").glob("*"))
        self.assertEqual(len(backups), 1)
        bdir = backups[0]
        self.assertEqual(stat.S_IMODE(bdir.stat().st_mode), 0o700)
        backed = bdir / ".aliases"
        self.assertEqual(backed.read_text(), "old content\n")
        self.assertEqual(stat.S_IMODE(backed.stat().st_mode), 0o600)

    def test_keys_and_local_never_touched(self):
        envdir = self.home / ".env"
        envdir.mkdir()
        keys = envdir / ".keys"
        keys.write_text("SENTINEL-KEYS")
        keys.chmod(0o600)
        local = envdir / ".local"
        local.write_text("SENTINEL-LOCAL")
        dangling = envdir / ".dangling"
        os.symlink("nonexistent", dangling)
        r = self.orch("shell")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(keys.read_text(), "SENTINEL-KEYS")
        self.assertEqual(stat.S_IMODE(keys.stat().st_mode), 0o600)
        self.assertEqual(local.read_text(), "SENTINEL-LOCAL")
        self.assertTrue(dangling.is_symlink() and not dangling.exists())

    def test_dangling_keys_symlink_untouched(self):
        envdir = self.home / ".env"
        envdir.mkdir()
        keys = envdir / ".keys"
        os.symlink("gone", keys)
        r = self.orch("shell")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(keys.is_symlink() and not keys.exists())

    def test_bashrc_symlink_refused(self):
        (self.home / "real-bashrc").write_text("x\n")
        os.symlink("real-bashrc", self.home / ".bashrc")
        r = self.orch("shell")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("symlink", r.stderr)
        self.assertFalse((self.home / ".env").exists())


class TestConfigureStage(Fixture):
    def setUp(self):
        super().setUp()
        self.stub("git", GIT_STUB)

    def test_configs_installed_and_include_added_once(self):
        (self.home / ".gitconfig").write_text(
            "[user]\n\tname = Work Name\n\temail = w@x\n"
            "[commit]\n\tgpgsign = true\n"
            "[include]\n\tpath = /other/path\n")
        for _ in range(2):
            r = self.orch("configure")
            self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("ctrlp_cmd",
                      (self.home / ".vimrc").read_text())
        self.assertTrue((self.home / ".config/terminator/config").is_file())
        snippet_path = self.home / ".config/basic-env/gitconfig"
        self.assertTrue(snippet_path.is_file())
        # installed snippet carries aliases/colors but no identity
        snippet_text = snippet_path.read_text()
        self.assertNotIn("[user]", snippet_text.lower())
        self.assertNotIn("name =", snippet_text)
        self.assertIn("view =", snippet_text)
        self.assertIn("ui = auto", snippet_text)
        env = dict(os.environ, HOME=str(self.home))
        out = subprocess.run(
            ["git", "config", "--global", "--get-all", "include.path"],
            capture_output=True, text=True, env=env).stdout.splitlines()
        snippet = str(snippet_path)
        self.assertEqual(out.count(snippet), 1, out)
        self.assertIn("/other/path", out)
        # check EFFECTIVE config (includes resolved): the snippet must
        # not override the machine's own identity/signing
        def eff(key):
            return subprocess.run(
                ["git", "config", "--includes", "--file",
                 str(self.home / ".gitconfig"), "--get", key],
                capture_output=True, text=True, env=env).stdout.strip()
        self.assertEqual(eff("user.name"), "Work Name")
        self.assertEqual(eff("user.email"), "w@x")
        self.assertEqual(eff("commit.gpgsign"), "true")

    def test_snippet_never_sets_identity_when_none_exists(self):
        (self.home / ".gitconfig").write_text("[core]\n\teditor = vim\n")
        r = self.orch("configure")
        self.assertEqual(r.returncode, 0, r.stderr)
        snippet_text = (self.home / ".config/basic-env/gitconfig").read_text()
        self.assertNotIn("[user]", snippet_text.lower())
        self.assertNotIn("name =", snippet_text)
        env = dict(os.environ, HOME=str(self.home))
        out = subprocess.run(
            ["git", "config", "--includes", "--file",
             str(self.home / ".gitconfig"), "--get", "user.name"],
            capture_output=True, text=True, env=env)
        self.assertEqual(out.stdout.strip(), "")
        self.assertNotEqual(out.returncode, 0)   # key genuinely unset

    def test_gitconfig_symlink_refused(self):
        (self.home / "real-gc").write_text("[user]\n\tname = X\n")
        os.symlink("real-gc", self.home / ".gitconfig")
        r = self.orch("configure")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("symlink", r.stderr)
        self.assertFalse((self.home / ".vimrc").exists())


class TestDryRunAndLifecycle(Fixture):
    def test_dry_run_creates_nothing(self):
        self.install_stubs()
        r = self.orch("all", "--dry-run")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("[dry-run]", r.stdout)
        self.assertEqual(list(self.home.iterdir()), [])

    def test_all_twice_no_duplicates(self):
        self.install_stubs(present=["git", "curl", "vim", "terminator",
                                    "eza", "batcat", "ctags"])
        (self.home / ".gitconfig").write_text("[user]\n\tname = T\n")
        for _ in range(2):
            r = self.orch("all")
            self.assertEqual(r.returncode, 0, r.stderr)
        bashrc = (self.home / ".bashrc").read_text()
        self.assertEqual(bashrc.count("# >>> basic-env >>>"), 1)
        env = dict(os.environ, HOME=str(self.home))
        out = subprocess.run(
            ["git", "config", "--global", "--get-all", "include.path"],
            capture_output=True, text=True, env=env).stdout.splitlines()
        snippet = str(self.home / ".config/basic-env/gitconfig")
        self.assertEqual(out.count(snippet), 1)
        # second run cloned nothing: clone count stable at first run's 22
        clones = [c for c in self.calls() if "|clone|" in c]
        self.assertEqual(len(clones), 22)
        # nothing needed installing -> no apt/sudo calls at all
        self.assertFalse(any(c.startswith("sudo|") for c in self.calls()))

    def test_home_with_spaces(self):
        spaced = self.tmp / "home with space"
        spaced.mkdir()
        self.home = spaced
        self.install_stubs(present=["git", "curl", "vim", "terminator",
                                    "eza", "batcat", "ctags"])
        r = self.orch("all")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((spaced / ".env/.setup").is_file())
        self.assertTrue((spaced / ".vimrc").is_file())



class TestShellStageEdgeCases(Fixture):
    def test_bashrc_without_trailing_newline(self):
        (self.home / ".bashrc").write_text("echo tail-no-newline")
        r = self.orch("shell")
        self.assertEqual(r.returncode, 0, r.stderr)
        text = (self.home / ".bashrc").read_text()
        self.assertEqual(text.count("# >>> basic-env >>>"), 1)
        # last original line got its own line, block starts on the next
        self.assertIn("echo tail-no-newline\n# >>> basic-env >>>", text)

    def test_malformed_markers_preserve_everything(self):
        for i, body in enumerate((
                "# >>> basic-env >>>\nif true; then\n",
                "echo x\n# <<< basic-env <<<\n",
                "# >>> basic-env >>\necho x\n",
                "# >>> basic-env >>>\n# >>> basic-env >>>\n# <<< basic-env <<<\n# <<< basic-env <<<\n")):
            sub = self.tmp / f"h{i}"
            sub.mkdir()
            home = sub / "home"
            home.mkdir()
            (home / ".bashrc").write_text(body)
            old_home = self.home
            self.home = home
            try:
                r = self.orch("shell")
            finally:
                self.home = old_home
            self.assertNotEqual(r.returncode, 0, body)
            self.assertIn("malformed", r.stderr, body)
            self.assertEqual((home / ".bashrc").read_text(), body)
            self.assertFalse((home / ".env").exists(), body)

    def test_bashrc_change_creates_private_backup_and_no_temps(self):
        (self.home / ".bashrc").write_text("orig content\n")
        r = self.orch("shell")
        self.assertEqual(r.returncode, 0, r.stderr)
        bdirs = list((self.home / ".local/state/basic-env/backups").glob("*"))
        self.assertEqual(len(bdirs), 1)
        backed = bdirs[0] / ".bashrc"
        self.assertEqual(backed.read_text(), "orig content\n")
        self.assertEqual(stat.S_IMODE(backed.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(bdirs[0].stat().st_mode), 0o700)
        # no atomic-rewrite leftovers beside .bashrc
        self.assertEqual(list(self.home.glob(".bashrc.*")), [])

    def test_rerun_is_byte_identical(self):
        (self.home / ".bashrc").write_text("# user stuff\nexport FOO=1\n")
        for _ in range(2):
            r = self.orch("shell")
            self.assertEqual(r.returncode, 0, r.stderr)
        first = (self.home / ".bashrc").read_bytes()
        r = self.orch("shell")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((self.home / ".bashrc").read_bytes(), first)
        self.assertEqual(first.count(b"# >>> basic-env >>>"), 1)

    def test_duplicate_marked_blocks_collapse(self):
        dup = ("# >>> basic-env >>>\nstale1\n# <<< basic-env <<<\n"
               "userline\n"
               "# >>> basic-env >>>\nstale2\n# <<< basic-env <<<\n")
        (self.home / ".bashrc").write_text(dup)
        r = self.orch("shell")
        self.assertEqual(r.returncode, 0, r.stderr)
        text = (self.home / ".bashrc").read_text()
        self.assertEqual(text.count("# >>> basic-env >>>"), 1)
        self.assertNotIn("stale1", text)
        self.assertNotIn("stale2", text)
        self.assertIn("userline", text)


class TestInstallEdgeCases(Fixture):
    def test_pathogen_symlink_dir_dangling_conflicts(self):
        for kind in ("dir", "symlink", "dangling"):
            sub = self.tmp / ("h-" + kind)
            home = sub / "home"
            (home / ".vim/autoload").mkdir(parents=True)
            target = home / ".vim/autoload/pathogen.vim"
            if kind == "dir":
                target.mkdir()
            elif kind == "symlink":
                real = home / "real-pathogen"
                real.write_text("x")
                os.symlink("real-pathogen", target)
            else:
                os.symlink("gone", target)
            old_home = self.home
            self.home = home
            self.install_stubs(present=["git", "curl", "vim", "terminator",
                                        "eza", "batcat", "ctags"])
            try:
                r = self.orch("install")
            finally:
                self.home = old_home
            self.assertNotEqual(r.returncode, 0, kind)
            self.assertIn("conflict", r.stderr, kind)

    def test_plugin_subdir_inside_parent_repo_is_conflict(self):
        bundle = self.home / ".vim/bundle"
        bundle.mkdir(parents=True)
        env = dict(os.environ, GIT_CONFIG_NOSYSTEM="1",
                   GIT_CONFIG_GLOBAL="/dev/null",
                   GIT_AUTHOR_NAME="T", GIT_AUTHOR_EMAIL="t@t",
                   GIT_COMMITTER_NAME="T", GIT_COMMITTER_EMAIL="t@t")
        subprocess.run(["git", "init", "-q"], cwd=bundle, env=env,
                       check=True, capture_output=True)
        (bundle / "supertab").mkdir()   # plain dir, inside parent repo
        self.install_stubs(present=["git", "curl", "vim", "terminator",
                                    "eza", "batcat", "ctags"])
        r = self.orch("install")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not a git checkout", r.stderr)

    def test_exuberant_ctags_requests_universal(self):
        self.stub("ctags", CTAGS_STUB)
        self.install_stubs(present=["git", "curl", "vim", "terminator",
                                    "eza", "batcat"])
        r = self.orch("install", CTAGS_VERSION="Exuberant Ctags 5.8")
        self.assertEqual(r.returncode, 0, r.stderr)
        apt = next(c for c in self.calls()
                   if "apt-get" in c and "install" in c)
        self.assertIn("universal-ctags", apt)

    def test_universal_ctags_satisfies(self):
        self.install_stubs(present=["git", "curl", "vim", "terminator",
                                    "eza", "batcat", "ctags"])
        r = self.orch("install")   # CTAGS_VERSION defaults to Universal
        self.assertEqual(r.returncode, 0, r.stderr)
        apt_calls = [c for c in self.calls()
                     if "apt-get" in c and "install" in c]
        self.assertFalse(any("universal-ctags" in c for c in apt_calls))

    @unittest.skipUnless(shutil.which("vim"), "real vim required")
    def test_helptags_real_vim_spaced_path(self):
        spaced = self.tmp / "home with space"
        plugin = spaced / ".vim/bundle/ctrlp.vim"   # a listed plugin
        (plugin / "doc").mkdir(parents=True)
        self.home = spaced
        # real vim visible via realbin (no stub), so helptags actually runs
        (self.realbin / "vim").symlink_to(shutil.which("vim"))
        self.install_stubs(present=["git", "curl", "terminator",
                                    "eza", "batcat", "ctags"])
        env = dict(os.environ, GIT_CONFIG_NOSYSTEM="1",
                   GIT_CONFIG_GLOBAL="/dev/null")
        subprocess.run(["git", "init", "-q"], cwd=plugin, env=env,
                       check=True, capture_output=True)
        (plugin / "doc/notes.txt").write_text("*ctrlp* sample\n")
        r = self.orch("install")
        self.assertEqual(r.returncode, 0, r.stderr)
        # fnameescape + env var survived the spaced HOME: tags were written
        self.assertTrue((plugin / "doc/tags").is_file())


class TestConfigureEdgeCases(Fixture):
    def test_missing_git_no_writes(self):
        r = self.orch("configure")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("git", r.stderr)
        self.assertFalse((self.home / ".vimrc").exists())
        self.assertFalse((self.home / ".config").exists())

    def test_dry_run_without_git_reports_intent(self):
        r = self.orch("configure", "--dry-run")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("[dry-run] would add include.path", r.stdout)
        self.assertFalse((self.home / ".vimrc").exists())

    def test_unparseable_gitconfig_refused_no_writes(self):
        (self.home / ".gitconfig").write_text("[unclosed\n")
        self.stub("git", GIT_STUB)
        r = self.orch("configure")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not a parseable", r.stderr)
        self.assertFalse((self.home / ".vimrc").exists())

    def test_git_config_global_target_never_written(self):
        xdg = self.tmp / "elsewhere-gitconfig"
        xdg.write_text("[user]\n\tname = Other\n")
        (self.home / ".gitconfig").write_text("[user]\n\tname = Mine\n")
        self.stub("git", GIT_STUB)
        r = self.orch("configure", GIT_CONFIG_GLOBAL=str(xdg))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(xdg.read_text(), "[user]\n\tname = Other\n")
        # include went to $HOME/.gitconfig
        env = dict(os.environ, HOME=str(self.home))
        out = subprocess.run(
            ["git", "config", "--file", str(self.home / ".gitconfig"),
             "--get-all", "include.path"],
            capture_output=True, text=True, env=env).stdout.splitlines()
        self.assertIn(str(self.home / ".config/basic-env/gitconfig"), out)

    def test_gitconfig_backed_up_before_include(self):
        orig = "[user]\n\tname = Mine\n"
        (self.home / ".gitconfig").write_text(orig)
        self.stub("git", GIT_STUB)
        r = self.orch("configure")
        self.assertEqual(r.returncode, 0, r.stderr)
        backups = list((self.home / ".local/state/basic-env/backups")
                       .glob("*/.gitconfig"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), orig)
        self.assertEqual(stat.S_IMODE(backups[0].stat().st_mode), 0o600)


class TestInvocation(Fixture):
    def test_bare_filename_invocation(self):
        r = subprocess.run([BASH, "setup_environment.sh", "--help"],
                           cwd=REPO, capture_output=True, text=True,
                           env=self.env())
        self.assertEqual(r.returncode, 0)
        self.assertIn("Usage:", r.stdout)

    def test_stage_script_from_scripts_dir(self):
        for s in ("install-tools.sh", "setup-shell.sh",
                  "configure-tools.sh"):
            r = subprocess.run([BASH, s, "--help"],
                               cwd=REPO / "scripts",
                               capture_output=True, text=True,
                               env=self.env())
            self.assertEqual(r.returncode, 0, s + r.stderr)
            self.assertIn("usage:", r.stdout)

if __name__ == "__main__":
    unittest.main()
