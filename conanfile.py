import os
import glob

from conans import ConanFile, tools, AutoToolsBuildEnvironment, RunEnvironment
from conans.errors import ConanInvalidConfiguration


class RConan(ConanFile):
    name = "rstatistics"
    version = '2.11.1'
    license = ("GPL-2", "GPL-3")
    url = "https://cran.r-project.org/src/base/"
    description = "A free software environment for statistical computing and graphics"
    homepage = "https://www.r-project.org"
    topics = ("conan", "statistics")
    settings = "os_build", "compiler", "arch_build"
    generators = "pkg_config"
    _source_subfolder = "source_subfolder"
    _autotools = None
    windows_installer=f'R-{version}-win64.exe'

    def source(self):
        if self.settings.os_build == "Windows":
            # Building on windows Is a royal pain... I'll just grab a build
            tools.download(
                url=f'https://artifactory.ccdc.cam.ac.uk:443/artifactory/ccdc-3rdparty-windows-runtime-exes/{self.windows_installer}',
                filename=self.windows_installer,
                sha256='25b2718004134a5aa6339d29ec77f96b99abcb0760beebcce0d09811bdce3a42',
                headers={
                'X-JFrog-Art-Api': os.environ.get("ARTIFACTORY_API_KEY", None)
            })
        else:
            tools.get(**self.conan_data["sources"][self.version])
            extrated_dir = "R-" + self.version
            os.rename(extrated_dir, self._source_subfolder)

    def build_requirements(self):
        if self.settings.os_build != 'Windows':
            self.build_requires('automake/1.16.1')
            self.build_requires('libjpeg/9d')
            self.build_requires('xz_utils/5.2.4')
            self.build_requires('libpng/1.6.37')
            self.build_requires('libtiff/4.1.0')
            self.build_requires('cairo/1.17.2')

    def system_requirements(self):
        installer = tools.SystemPackageTool()
        if tools.os_info.is_linux:
            if tools.os_info.with_yum:
                installer.install(f"devtoolset-{self.settings.compiler.version.value}-gcc-gfortran")
            else:
                installer.install("gfortran")
                installer.install(f"libgfortran-{self.settings.compiler.version.value}-dev")
        if tools.os_info.is_macos:
            try:
                installer.install("gcc", update=True, force=True)
            except Exception:
                self.output.warn("brew install gcc failed. Tying to fix it with 'brew link'")
                self.run("brew link --overwrite gcc")

    def _configure_autotools(self, envbuild_vars):
        if self._autotools:
            return self._autotools
        self._autotools = AutoToolsBuildEnvironment(self, win_bash=tools.os_info.is_windows)
        args = [
            "--disable-nls",
            "--disable-R-shlib",
            "--disable-R-static-lib",
            "--with-x=no",
            "--with-aqua=no",
            "--with-tcltk=no",
            "--with-cairo=yes",
            "--with-readline=no",
        ]
        if tools.os_info.is_macos:
            args.extend(['--disable-R-framework'])

        self._autotools.configure(configure_dir=self._source_subfolder, args=args, vars=envbuild_vars)
        return self._autotools

    def build(self):
        if self.settings.os_build == "Windows":
            pass

        env_build = RunEnvironment(self)
        with tools.environment_append(env_build.vars):
            autotools = self._configure_autotools(env_build.vars)
            autotools.make()

    def package(self):
        if self.settings.os_build == "Windows":
            tools.run(f'{self.windows_installer} /VERYSILENT /DIR={self.package_folder}')
        else:
            env_build = RunEnvironment(self)
            with tools.environment_append(env_build.vars):
                autotools = self._configure_autotools(env_build.vars)
                autotools.install()

            self.copy("COPYING", dst="licenses", src=self._source_subfolder)
            # Fix paths in wrapper script
            for r_filename, relative_path in [
                ( os.path.join( 'bin', 'R'), '..' ),
                ( os.path.join( 'bin', 'R64'), '..' ),
                ( os.path.join( 'lib', 'R', 'bin', 'R'), '../../..'),
                ( os.path.join( 'lib', 'R', 'bin', 'R64'), '../../..'),
                ( os.path.join( 'lib64', 'R', 'bin', 'R'), '../../..'),
                ( os.path.join( 'lib64', 'R', 'bin', 'R64'), '../../..'),
                ]:
                r_filename = os.path.join(self.package_folder, r_filename)
                if not os.path.exists(r_filename):
                    continue
                tools.replace_in_file(r_filename, 
                    'R_HOME_DIR=', 
                    f'R_INSTALL_DIR=`dirname $0`/{relative_path} \nR_HOME_DIR=')
                tools.replace_in_file(r_filename, os.path.abspath(str(self.package_folder)), '${R_INSTALL_DIR}')

        if tools.os_info.is_macos:
            self.copy("/usr/local/opt/gcc/lib/gcc/9/libgfortran.5.dylib", dst="lib/R/lib")
            self.copy("/usr/local/opt/gcc/lib/gcc/9/libquadmath.0.dylib", dst="lib/R/lib")
        if tools.os_info.is_linux:
            if tools.os_info.with_yum:
                self.copy("/lib64/libgfortran.so.5", dst="lib/R/lib")
                self.copy("/lib64/libquadmath.so.0", dst="lib/R/lib")
                self.copy("/lib64/liblzma.so.5", dst="lib/R/lib")

        tools.rmdir(os.path.join(self.package_folder, "lib", "R", "doc"))
        tools.rmdir(os.path.join(self.package_folder, "share"))

    def package_id(self):
        del self.info.settings.compiler

    def package_info(self):
        bin_path = os.path.join(self.package_folder, 'bin')
        self.output.info('Appending PATH environment variable: %s' % bin_path)
        self.env_info.PATH.append(bin_path)
