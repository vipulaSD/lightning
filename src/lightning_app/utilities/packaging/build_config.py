import inspect
import logging
import os
from dataclasses import asdict, dataclass
from types import FrameType
from typing import cast, List, Optional, TYPE_CHECKING, Union

from pkg_resources import parse_requirements

if TYPE_CHECKING:
    from lightning_app import LightningWork
    from lightning_app.utilities.packaging.cloud_compute import CloudCompute


logger = logging.getLogger(__name__)


@dataclass
class BuildConfig:
    """The Build Configuration describes how the environment a LightningWork runs in should be set up.

    Arguments:
        requirements: List of requirements or paths to requirement files.
        dockerfile: The path to a dockerfile to be used to build your container.
            You need to add those lines to ensure your container works in the cloud.

            .. warning:: This feature isn't supported yet, but coming soon.

            Example::

                WORKDIR /gridai/project
                COPY . .

            Learn more by checking out:
            https://docs.grid.ai/features/runs/running-experiments-with-a-dockerfile
        image: The base image that the work runs on. This should be a publicly accessible image from a registry that
            doesn't enforce rate limits (such as DockerHub) to pull this image, otherwise your application will not
            start.
    """

    requirements: Optional[Union[str, List[str]]] = None
    dockerfile: Optional[str] = None
    image: Optional[str] = None

    def __post_init__(self):
        self._call_dir = os.path.dirname(cast(FrameType, inspect.currentframe()).f_back.f_back.f_code.co_filename)
        self._prepare_requirements()
        self._prepare_dockerfile()

    def build_commands(self) -> List[str]:
        """Override to run some commands before your requirements are installed.

        .. note:: If you provide your own dockerfile, this would be ignored.

        .. doctest::

            from dataclasses import dataclass
            from lightning_app import BuildConfig

            @dataclass
            class MyOwnBuildConfig(BuildConfig):

                def build_commands(self):
                    return ["sudo apt-get install libsparsehash-dev"]

            BuildConfig(requirements=["git+https://github.com/mit-han-lab/torchsparse.git@v1.4.0"])
        """
        return []

    def on_work_init(self, work, cloud_compute: Optional["CloudCompute"] = None):
        """Override with your own logic to load the requirements or dockerfile."""
        try:
            self.requirements = sorted(self.requirements or self._find_requirements(work) or [])
            self.dockerfile = self.dockerfile or self._find_dockerfile(work)
        except TypeError:
            logger.debug("The provided work couldn't be found.")

    def _find_requirements(self, work: "LightningWork") -> List[str]:
        # 1. Get work file
        file = inspect.getfile(work.__class__)

        # 2. Try to find a requirement file associated the file.
        dirname = os.path.dirname(file)
        requirement_files = [os.path.join(dirname, f) for f in os.listdir(dirname) if f == "requirements.txt"]
        if not requirement_files:
            return []
        try:
            requirements = list(map(str, parse_requirements(open(requirement_files[0]).readlines())))
        except NotADirectoryError:
            requirements = []
        return [r for r in requirements if r != "lightning"]

    def _find_dockerfile(self, work: "LightningWork") -> List[str]:
        # 1. Get work file
        file = inspect.getfile(work.__class__)

        # 2. Check for Dockerfile.
        dirname = os.path.dirname(file)
        dockerfiles = [os.path.join(dirname, f) for f in os.listdir(dirname) if f == "Dockerfile"]

        if not dockerfiles:
            return []

        # 3. Read the dockerfile
        with open(dockerfiles[0]) as f:
            dockerfile = list(f.readlines())
        return dockerfile

    def _prepare_requirements(self) -> Optional[Union[str, List[str]]]:
        if not self.requirements:
            return None

        requirements = []
        for req in self.requirements:
            # 1. Check for relative path
            path = os.path.join(self._call_dir, req)
            if os.path.exists(path):
                try:
                    requirements.extend(list(map(str, parse_requirements(open(path).readlines()))))
                except NotADirectoryError:
                    pass
            else:
                requirements.append(req)

        self.requirements = requirements

    def _prepare_dockerfile(self):
        if self.dockerfile:
            dockerfile_path = os.path.join(self._call_dir, self.dockerfile)
            if os.path.exists(dockerfile_path):
                with open(dockerfile_path) as f:
                    self.dockerfile = list(f.readlines())

    def to_dict(self):
        return {"__build_config__": asdict(self)}

    @classmethod
    def from_dict(cls, d):
        return cls(**d["__build_config__"])
