""" Tools to manage tsrc workspaces

Mostly used by tsrc/cli.py

"""

import stat

from tsrc import ui
import tsrc
import tsrc.executor
import tsrc.git
import tsrc.manifest


class Workspace():
    def __init__(self, root_path):
        self.root_path = root_path
        hidden_path = self.joinpath(".tsrc")
        self.manifest_clone_path = hidden_path.joinpath("manifest")
        self.manifest = None

    def get_repos(self):
        assert self.manifest, "manifest is empty. Did you call load_manifest()?"
        return self.manifest.repos

    def joinpath(self, *parts):
        return self.root_path.joinpath(*parts)

    def load_manifest(self):
        manifest_yml_path = self.manifest_clone_path.joinpath("manifest.yml")
        if not manifest_yml_path.exists():
            message = "No manifest found in {}. Did you run `tsrc init` ?"
            raise tsrc.Error(message.format(manifest_yml_path))
        self.manifest = tsrc.manifest.Manifest()
        self.manifest.load(manifest_yml_path.text())

    def get_gitlab_url(self):
        gitlab_config = self.manifest.gitlab
        if not gitlab_config:
            raise tsrc.Error("No gitlab configuration found in manifest")
        res = gitlab_config.get("url")
        if not res:
            raise tsrc.Error("Missing 'url' in gitlab configuration")
        return res

    def init_manifest(self, manifest_url, *, branch="master", tag=None):
        if self.manifest_clone_path.exists():
            ui.warning("Re-initializing worktree")
            tsrc.git.run_git(self.manifest_clone_path,
                             "remote", "set-url", "origin",
                             manifest_url)

            tsrc.git.run_git(self.manifest_clone_path, "fetch")
            tsrc.git.run_git(self.manifest_clone_path, "checkout",
                             "-B", branch)
            tsrc.git.run_git(self.manifest_clone_path, "branch",
                             branch, "--set-upstream-to", "origin/%s" % branch)
            if tag:
                ref = tag
            else:
                ref = "origin/%s" % branch
            tsrc.git.run_git(self.manifest_clone_path, "reset", "--hard", ref)
        else:
            parent, name = self.manifest_clone_path.splitpath()
            parent.makedirs_p()
            tsrc.git.run_git(self.manifest_clone_path.parent, "clone",
                             manifest_url, name, "--branch", branch)
            if tag:
                tsrc.git.run_git(self.manifest_clone_path, "reset",
                                 "--hard", tag)

        self.load_manifest()

    def update_manifest(self):
        ui.info_2("Updating manifest")
        if not self.manifest_clone_path.exists():
            message = "Could not find manifest in {}. "
            message += "Did you run `tsrc init` ?"
            raise tsrc.Error(message.format(self.manifest_clone_path))
        cmd = ("fetch", "--prune", "origin")
        tsrc.git.run_git(self.manifest_clone_path, *cmd)
        cmd = ("reset", "--hard", "@{u}")
        tsrc.git.run_git(self.manifest_clone_path, *cmd)

    def manifest_branch(self):
        return tsrc.git.get_current_branch(self.manifest_clone_path)

    def clone_missing(self):
        """ Clone missing repos.

        Called at the beginning of `tsrc init` and `tsrc sync`

        """
        to_clone = list()
        for repo in self.get_repos():
            repo_path = self.joinpath(repo.src)
            if not repo_path.exists():
                to_clone.append(repo)
        cloner = Cloner(self)
        tsrc.executor.run_sequence(to_clone, cloner)

    def set_remotes(self):
        remote_setter = RemoteSetter(self)
        tsrc.executor.run_sequence(self.get_repos(), remote_setter)

    def copy_files(self):
        file_copier = FileCopier(self)
        tsrc.executor.run_sequence(self.manifest.copyfiles, file_copier)

    def enumerate_repos(self):
        """ Yield (index, repo, full_path) for all the repos """
        for i, repo in enumerate(self.get_repos()):
            full_path = self.joinpath(repo.src)
            yield (i, repo, full_path)

    def get_url(self, src):
        """ Return the url of the project in `src` """
        return self.manifest.get_url(src)


# pylint: disable=too-few-public-methods
class Cloner(tsrc.executor.Actor):
    def __init__(self, workspace):
        self.workspace = workspace

    def description(self):
        return "Cloning missing repos"

    def display_item(self, repo):
        return repo.src

    def process(self, repo):
        ui.info(repo.src)
        repo_path = self.workspace.joinpath(repo.src)
        parent, name = repo_path.splitpath()
        parent.makedirs_p()
        try:
            tsrc.git.run_git(parent, "clone", repo.url, "--branch", repo.branch, name)
        except tsrc.Error:
            raise tsrc.Error("Cloning failed")
        ref = repo.fixed_ref
        if ref:
            ui.info_2("Resetting", repo.src, "to", ref)
            try:
                tsrc.git.run_git(repo_path, "reset", "--hard", ref)
            except tsrc.Error:
                raise tsrc.Error("Resetting to", ref, "failed")


class FileCopier(tsrc.executor.Actor):
    def __init__(self, workspace):
        self.workspace = workspace

    def description(self):
        return "Copying files"

    def display_item(self, item):
        src, dest = item
        return "%s -> %s" % (src, dest)

    def process(self, item):
        src, dest = item
        ui.info(src, "->", dest)
        try:
            src_path = self.workspace.joinpath(src)
            dest_path = self.workspace.joinpath(dest)
            if dest_path.exists():
                # Re-set the write permissions on the file:
                dest_path.chmod(stat.S_IWRITE)
            src_path.copy(dest_path)
            # Make sure perms are read only for everyone
            dest_path.chmod(0o10444)
        except Exception as e:
            raise tsrc.Error(str(e))


class RemoteSetter(tsrc.executor.Actor):
    def __init__(self, workspace):
        self.workspace = workspace

    def description(self):
        return "Setting remote URLs"

    def display_item(self, repo):
        return repo.src

    def process(self, repo):
        full_path = self.workspace.joinpath(repo.src)
        try:
            _, old_url = tsrc.git.run_git(full_path, "remote", "get-url", "origin", raises=False)
            if old_url != repo.url:
                ui.info_2(repo.src, old_url, "->", repo.url)
                tsrc.git.run_git(full_path, "remote", "set-url", "origin", repo.url)
        except Exception:
            raise tsrc.Error(repo.src, ":", "Failed to set remote url to %s" % repo.url)
