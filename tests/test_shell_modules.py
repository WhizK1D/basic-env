#!/usr/bin/env python3
"""Regression tests for the basic-env public shell modules.

Uses only the stdlib. All shell invocations are isolated: fake PATH stubs
stand in for eza/bat/batcat/git/sudo/apt-get/tar, and temporary HOME
directories carry no real user config or key material.
"""

import os
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SHELL_DIR = REPO / "shell"
PUBLIC_SHELL_FILES = [
    SHELL_DIR / "setup",
    SHELL_DIR / "colors",
    SHELL_DIR / "aliases",
    SHELL_DIR / "prompt",
    REPO / "bashrc",
]
# public source name -> installed runtime dotfile name under ~/.env
RUNTIME_NAMES = {"setup": ".setup", "colors": ".colors",
                 "aliases": ".aliases", "prompt": ".prompt"}
BASH = "/bin/bash"


def run_bash(script, env=None, interactive=False):
    cmd = [BASH, "--noprofile", "--norc"]
    if interactive:
        cmd.append("-i")
    cmd += ["-c", script]
    return subprocess.run(
        cmd, capture_output=True, text=True, env=env, timeout=30
    )


def make_stub(directory, name, body=None):
    """Create an executable stub that logs one argv per line to
    $STUB_LOG_DIR/<name>.args, or runs a custom body."""
    p = Path(directory) / name
    if body is None:
        body = (
            "#!/bin/sh\n"
            '[ -n "$STUB_LOG_DIR" ] && printf \'%s\\n\' "$@" '
            f'> "$STUB_LOG_DIR/{name}.args"\n'
        )
    p.write_text(body)
    p.chmod(0o755)
    return p


def read_args(logdir, name):
    f = Path(logdir) / f"{name}.args"
    if not f.exists():
        return None
    return f.read_text().splitlines()


class TempFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="basic-env-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.fakebin = self.tmp / "bin"
        self.fakebin.mkdir()
        self.logdir = self.tmp / "logs"
        self.logdir.mkdir()
        self.home = self.tmp / "home"
        self.home.mkdir()

    def env(self, path=None):
        e = {
            "PATH": str(path if path is not None else self.fakebin),
            "STUB_LOG_DIR": str(self.logdir),
            "HOME": str(self.home),
            "TERM": "xterm",
        }
        return e


class TestSyntax(unittest.TestCase):
    def test_bash_n_all_public_shell_files(self):
        for f in PUBLIC_SHELL_FILES:
            with self.subTest(file=f):
                r = subprocess.run(
                    [BASH, "--noprofile", "--norc", "-n", str(f)],
                    capture_output=True, text=True,
                )
                self.assertEqual(r.returncode, 0, f"{f}: {r.stderr}")


class TestAliases(TempFixture):
    def _populate(self, tools):
        for t in tools:
            if t == "cat":
                make_stub(self.fakebin, "cat",
                          '#!/bin/sh\nexec /bin/cat "$@"\n')
            else:
                make_stub(self.fakebin, t)

    def _source_and_query(self, query):
        script = (
            f'. "{SHELL_DIR}/aliases"\n'
            f'{query}'
        )
        return run_bash(script, env=self.env())

    def test_eza_and_batcat_present(self):
        self._populate(["eza", "batcat", "cat"])
        r = self._source_and_query('alias ls; alias l; alias la; alias ll; alias cat; alias bat; alias dcat')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("alias ls='eza ", r.stdout)
        self.assertIn("alias ll='eza -la", r.stdout)
        self.assertIn("alias cat='batcat --paging=never'", r.stdout)
        self.assertIn("alias bat='batcat'", r.stdout)
        self.assertIn("alias dcat='command cat'", r.stdout)

    def test_eza_and_bat_present(self):
        self._populate(["eza", "bat", "cat"])
        r = self._source_and_query('alias ls; alias cat; alias bat')
        self.assertIn("alias ls='eza ", r.stdout)
        self.assertIn("alias cat='bat --paging=never'", r.stdout)
        # native bat exists: we must not define a bat alias ourselves
        self.assertNotIn("alias bat=", r.stdout)

    def test_neither_present_falls_back(self):
        self._populate(["cat"])
        r = self._source_and_query('alias ls; alias ll; alias cat; echo "cat_rc=$?"; alias dcat')
        self.assertIn("alias ls='ls --color=auto'", r.stdout)
        self.assertIn("alias ll='ls -l", r.stdout)
        self.assertIn("cat_rc=1", r.stdout)          # no stale cat alias
        self.assertIn("alias dcat='command cat'", r.stdout)

    def test_resourcing_after_dependency_disappearance(self):
        self._populate(["eza", "batcat", "cat"])
        gone = self.tmp / "gone-bin"
        gone.mkdir()
        r = run_bash(
            f'PATH="{self.fakebin}"\n'
            f'. "{SHELL_DIR}/aliases"\n'
            'alias ls; alias cat; alias bat\n'
            f'PATH="{gone}"\n'
            f'. "{SHELL_DIR}/aliases"\n'
            'alias ls; alias cat 2>/dev/null; echo "cat_rc=$?"; '
            'alias bat 2>/dev/null; echo "bat_rc=$?"',
            env=self.env(),
        )
        lines = r.stdout
        # first pass: eza/batcat aliases
        self.assertIn("alias ls='eza ", lines)
        self.assertIn("alias cat='batcat --paging=never'", lines)
        self.assertIn("alias bat='batcat'", lines)
        # after re-source with tools gone: standard ls, stale cat/bat cleared
        self.assertIn("alias ls='ls --color=auto'", lines)
        self.assertIn("cat_rc=1", lines)
        self.assertIn("bat_rc=1", lines)

    def test_dcat_preserves_bytes(self):
        self._populate(["batcat", "cat"])
        payload = self.tmp / "payload.bin"
        payload.write_bytes(b"\x00binary\x01\xff no trailing newline")
        script = (
            'shopt -s expand_aliases\n'
            f'. "{SHELL_DIR}/aliases"\n'
            f'dcat "{payload}"'
        )
        r = subprocess.run(
            [BASH, "--noprofile", "--norc", "-c", script],
            capture_output=True, env=self.env(), timeout=30,
        )
        self.assertEqual(r.returncode, 0, r.stderr.decode())
        self.assertEqual(r.stdout, payload.read_bytes())


# git stub: delegate check-ref-format to real git for authentic validation;
# record argv (one arg per line) for everything else.
GIT_STUB = (
    "#!/bin/sh\n"
    'if [ "$1" = "check-ref-format" ]; then exec /usr/bin/git "$@"; fi\n'
    '[ -n "$STUB_LOG_DIR" ] && printf \'%s\\n\' "$@" > "$STUB_LOG_DIR/git.args"\n'
    "exit 0\n"
)


class TestFunctions(TempFixture):
    def _run_fn(self, call, tools=()):
        for t in tools:
            if t == "git":
                make_stub(self.fakebin, "git", GIT_STUB)
            else:
                make_stub(self.fakebin, t)
        script = f'. "{SHELL_DIR}/aliases"\n{call}'
        return run_bash(script, env=self.env())

    def test_gva_default_count(self):
        r = self._run_fn("gva", tools=["git"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(read_args(self.logdir, "git"), ["view", "--all", "-n", "5"])

    def test_gva_explicit_count(self):
        r = self._run_fn("gva 17", tools=["git"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(read_args(self.logdir, "git"), ["view", "--all", "-n", "17"])

    def test_gva_rejects_bad_args(self):
        for bad in ("gva foo", "gva -1", "gva '3;rm'", "gva 1 2"):
            r = self._run_fn(bad, tools=["git"])
            self.assertEqual(r.returncode, 2, f"{bad}: {r.stdout} {r.stderr}")
            self.assertIsNone(read_args(self.logdir, "git"), bad)

    def test_gp_default_pushes_master(self):
        r = self._run_fn("gp", tools=["git"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(read_args(self.logdir, "git"), ["push", "origin", "HEAD:master"])

    def test_gp_explicit_branch_quoted(self):
        r = self._run_fn("gp feature/my-branch", tools=["git"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(read_args(self.logdir, "git"),
                         ["push", "origin", "HEAD:feature/my-branch"])

    @unittest.skipUnless(shutil.which("git"), "real git needed for ref validation")
    def test_gp_accepts_nonascii_branch(self):
        r = self._run_fn("gp 'feature/üñí-çode'", tools=["git"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(read_args(self.logdir, "git"),
                         ["push", "origin", "HEAD:feature/üñí-çode"])

    def test_gp_rejects_bad_args(self):
        for bad in ("gp 'a b'", "gp -x", "gp a b", "gp ''", "gp 'a..b'"):
            r = self._run_fn(bad, tools=["git"])
            self.assertNotEqual(r.returncode, 0, bad)
            self.assertIsNone(read_args(self.logdir, "git"), bad)

    def test_sin_requires_args_and_quotes(self):
        r = self._run_fn("sin", tools=["sudo"])
        self.assertEqual(r.returncode, 2)
        self.assertIsNone(read_args(self.logdir, "sudo"))

    def test_sin_forwards_args_verbatim(self):
        r = self._run_fn("sin pkg-a 'pkg b'", tools=["sudo"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(read_args(self.logdir, "sudo"),
                         ["apt-get", "install", "pkg-a", "pkg b"])

    def test_extract_quotes_path_with_spaces(self):
        make_stub(self.fakebin, "tar")
        d = self.tmp / "dir with spaces"
        d.mkdir()
        f = d / "a file.tar.gz"
        f.write_bytes(b"x")
        r = self._run_fn(f'extract "{f}"')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(read_args(self.logdir, "tar"), ["xvzf", str(f)])

    def test_extract_anchors_relative_paths(self):
        make_stub(self.fakebin, "tar")
        d = self.tmp / "rel dir"
        d.mkdir()
        f = d / "a file.tar.gz"
        f.write_bytes(b"x")
        rel = os.path.relpath(f, self.tmp)
        r = self._run_fn(f'cd "{self.tmp}"\nextract "{rel}"')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(read_args(self.logdir, "tar"), ["xvzf", f"./{rel}"])

    def test_extract_rejects_missing_and_unknown(self):
        r = self._run_fn('extract "/nonexistent.tar.gz"')
        self.assertEqual(r.returncode, 1)
        f = self.tmp / "notes.txt"
        f.write_text("x")
        r = self._run_fn(f'extract "{f}"')
        self.assertEqual(r.returncode, 1)
        r = self._run_fn("extract")
        self.assertEqual(r.returncode, 2)

    @unittest.skipUnless(shutil.which("unzip"), "real unzip required")
    def test_extract_zip_with_space_and_leading_hyphen(self):
        realbin = self.tmp / "realbin"
        realbin.mkdir()
        for t in ("unzip", "mkdir", "rm"):
            (realbin / t).symlink_to(shutil.which(t))
        for name in ("with space.zip", "-leading.zip"):
            work = self.tmp / ("zw-" + name.replace(" ", "_").lstrip("-"))
            work.mkdir()
            with zipfile.ZipFile(work / name, "w") as z:
                z.writestr("x.txt", "payload")
            script = (
                f'. "{SHELL_DIR}/aliases"\n'
                f'cd "{work}"\n'
                f'extract "{name}"'
            )
            r = run_bash(script, env=self.env(path=realbin))
            self.assertEqual(r.returncode, 0, f"{name}: {r.stderr}")
            self.assertEqual((work / "x.txt").read_text(), "payload")


class TestSetupEntrypoint(TempFixture):
    def _make_envdir(self, extra=()):
        envdir = self.home / ".env"
        envdir.mkdir()
        for pub, runtime in RUNTIME_NAMES.items():
            shutil.copy2(SHELL_DIR / pub, envdir / runtime)
        for name in extra:
            (envdir / name).write_text(
                f'{name.strip(".").upper().replace("-","_")}_MARKER=1\n'
            )
        return envdir

    def test_noninteractive_source_does_nothing(self):
        envdir = self._make_envdir()
        r = run_bash(
            f'. "{envdir}/.setup"\n'
            'type -t gva >/dev/null && echo GVA || echo NO_GVA\n'
            'alias ls >/dev/null 2>&1 && echo LS_ALIAS || echo NO_LS_ALIAS',
            env=self.env(),
        )
        self.assertIn("NO_GVA", r.stdout)
        self.assertIn("NO_LS_ALIAS", r.stdout)

    def test_interactive_sources_explicit_files_only(self):
        envdir = self._make_envdir()
        (envdir / ".keys").write_text('KEYS_MARKER=1\n')
        (envdir / ".local").write_text('LOCAL_MARKER=1\n')
        (envdir / ".evil").write_text('EVIL_MARKER=1\n')
        script = (
            f'. "{envdir}/.setup"\n'
            'echo "KEYS=$KEYS_MARKER LOCAL=$LOCAL_MARKER EVIL=${EVIL_MARKER-unset}"\n'
            'type -t gva >/dev/null && echo GVA_OK\n'
            'alias cat 2>/dev/null || echo NO_CAT\n'
            'echo "ROOT=${ROOT-unset} DIR=${basic_env_dir-unset}"'
        )
        r = run_bash(script, env=self.env(), interactive=True)
        self.assertIn("KEYS=1", r.stdout)
        self.assertIn("LOCAL=1", r.stdout)
        self.assertIn("EVIL=unset", r.stdout)
        self.assertIn("GVA_OK", r.stdout)
        self.assertIn("ROOT=unset", r.stdout)
        self.assertIn("DIR=unset", r.stdout)

    def test_missing_optional_files_ok(self):
        envdir = self._make_envdir()
        r = run_bash(
            f'. "{envdir}/.setup"; type -t gva >/dev/null && echo GVA_OK',
            env=self.env(), interactive=True,
        )
        self.assertIn("GVA_OK", r.stdout)


@unittest.skipUnless(shutil.which("git"), "git required for prompt tests")
class TestGitPrompt(TempFixture):
    GIT_ENV_EXTRA = {
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "T",
        "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "T",
        "GIT_COMMITTER_EMAIL": "t@example.com",
    }

    def setUp(self):
        super().setUp()
        if not Path("/usr/lib/git-core/git-sh-prompt").exists():
            self.skipTest("git-sh-prompt helper not installed")

    def _git(self, *args, cwd=None):
        env = dict(os.environ)
        env.update(self.GIT_ENV_EXTRA)
        subprocess.run(
            ["git", "-c", "user.name=T", "-c", "user.email=t@example.com",
             *args],
            cwd=cwd or self.repo, env=env, check=True,
            capture_output=True, text=True,
        )

    def _prompt_output(self, cwd):
        script = (
            f'. "{SHELL_DIR}/colors"\n. "{SHELL_DIR}/prompt"\n'
            f'cd "{cwd}"\nbasic_env_git_prompt'
        )
        env = dict(os.environ)
        env.update(self.GIT_ENV_EXTRA)
        r = run_bash(script, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def _init_repo(self, commits=1):
        self.repo = self.tmp / "repo"
        self.repo.mkdir(exist_ok=True)
        env = dict(os.environ)
        env.update(self.GIT_ENV_EXTRA)
        subprocess.run(["git", "init", "-b", "main"], cwd=self.repo,
                       env=env, check=True, capture_output=True)
        for i in range(commits):
            (self.repo / "f.txt").write_text(f"v{i}\n")
            self._git("add", "f.txt")
            self._git("commit", "-m", f"c{i}")

    def test_branch_from_nested_dir(self):
        self._init_repo()
        nested = self.repo / "a" / "b"
        nested.mkdir(parents=True)
        self.assertEqual(self._prompt_output(nested), "(main)")

    def test_nonrepo_empty(self):
        d = self.tmp / "plain"
        d.mkdir()
        self.assertEqual(self._prompt_output(d), "")

    def test_unborn_head(self):
        self.repo = self.tmp / "unborn"
        self.repo.mkdir()
        env = dict(os.environ)
        env.update(self.GIT_ENV_EXTRA)
        subprocess.run(["git", "init", "-b", "main"], cwd=self.repo,
                       env=env, check=True, capture_output=True)
        self.assertEqual(self._prompt_output(self.repo), "(main)")

    def test_detached_head(self):
        self._init_repo()
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=self.repo,
            env={**os.environ, **self.GIT_ENV_EXTRA},
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        self._git("checkout", "--detach", sha)
        out = self._prompt_output(self.repo)
        self.assertTrue(
            sha[:7] in out or "detached" in out.lower(),
            f"unexpected detached prompt: {out!r}",
        )

    def test_linked_worktree(self):
        self._init_repo()
        wt = self.tmp / "wt"
        self._git("worktree", "add", "-b", "wtbranch", str(wt))
        self.assertEqual(self._prompt_output(wt), "(wtbranch)")

    def test_merge_state_indicator(self):
        self._init_repo()
        (self.repo / "f.txt").write_text("main\n")
        self._git("checkout", "-b", "feature")
        (self.repo / "f.txt").write_text("feature\n")
        self._git("commit", "-am", "feature")
        self._git("checkout", "main")
        (self.repo / "f.txt").write_text("mainline\n")
        self._git("commit", "-am", "mainline")
        env = dict(os.environ)
        env.update(self.GIT_ENV_EXTRA)
        subprocess.run(["git", "merge", "feature"], cwd=self.repo,
                       env=env, capture_output=True)  # conflicts expected
        out = self._prompt_output(self.repo)
        self.assertIn("MERGING", out)

    def test_ps1_shows_prior_exit_status(self):
        script = (
            f'. "{SHELL_DIR}/colors"\n. "{SHELL_DIR}/prompt"\n'
            'cd /\n'
            'false; e1="${PS1@P}"\n'
            'true;  e0="${PS1@P}"\n'
            'printf "%s\\n==\\n%s\\n" "$e1" "$e0"'
        )
        r = run_bash(script, env=self.env("/usr/bin:/bin"))
        self.assertEqual(r.returncode, 0, r.stderr)
        e1, e0 = r.stdout.split("\n==\n")
        self.assertRegex(e1, r"\[1\]")
        self.assertRegex(e0, r"\[0\]")


if __name__ == "__main__":
    unittest.main()
