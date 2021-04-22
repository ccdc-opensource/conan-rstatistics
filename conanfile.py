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
            self.build_requires('automake/1.16.2')
            self.build_requires('libjpeg/9d')
            self.build_requires('xz_utils/5.2.5')
            self.build_requires('libpng/1.6.37')
            self.build_requires('libtiff/4.2.0')
            self.build_requires('cairo/1.17.2')

        installer = tools.SystemPackageTool()
        if tools.os_info.is_linux:
            if tools.os_info.with_yum:
                installer.install(f"devtoolset-{self.settings.compiler.version.value}-gcc-gfortran")
            else:
                installer.install("gfortran")
                installer.install(f"libgfortran-{self.settings.compiler.version.value}-dev")
        if tools.os_info.is_macos:
            try:
                installer.install("gcc@9", update=True, force=True)
            except Exception:
                self.output.warn("brew install gcc failed. Tying to fix it with 'brew link'")
                self.run("brew link --overwrite gcc")
            if not os.path.islink('/usr/local/bin/gfortran'):
                self.output.warn("Linking /usr/local/bin/gfortran -> gfortran-9")
                os.symlink('gfortran-9', '/usr/local/bin/gfortran')

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

        # gcc 10 has made -fno-common default
        # see https://gcc.gnu.org/gcc-10/porting_to.html
        v = tools.Version(str(self.settings.compiler.version))
        if self.settings.compiler == "gcc" and (v >= "10.0"):
            self.autotools.flags.append('-fcommon')

        self._autotools.configure(configure_dir=self._source_subfolder, args=args, vars=envbuild_vars)
        return self._autotools

    def build(self):
        if self.settings.os_build == "Windows":
            return

        env_build = RunEnvironment(self)
        with tools.environment_append(env_build.vars):
            autotools = self._configure_autotools(env_build.vars)
            autotools.make()

    def package(self):
        if self.settings.os_build == "Windows":
            self.run(f'{self.windows_installer} /VERYSILENT /DIR={self.package_folder}')
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
            # the package must be self consistent, otherwise scripts fail badly
            gcc_pkg = "/usr/local/opt/gcc@9/lib/gcc/9"
            self.copy("libgfortran.5.dylib", src=gcc_pkg, dst="lib/R/lib")
            self.copy("libquadmath.0.dylib", src=gcc_pkg, dst="lib/R/lib")
            for macho in [
                'lib/R/bin/exec/R',
                'lib/R/library/cluster/libs/cluster.so',
                'lib/R/library/mgcv/libs/mgcv.so',
                'lib/R/library/Matrix/libs/Matrix.so',
                'lib/R/library/KernSmooth/libs/KernSmooth.so',
                'lib/R/library/stats/libs/stats.so',
                'lib/R/modules/lapack.so',
                'lib/R/lib/libRlapack.dylib',
            ]:
                in_pkg = os.path.join(self.package_folder, macho)
                self.run(f'/usr/bin/install_name_tool -change {gcc_pkg}/libgfortran.5.dylib @rpath/libgfortran.5.dylib {in_pkg}')
                self.run(f'/usr/bin/install_name_tool -change {gcc_pkg}/libquadmath.0.dylib @rpath/libquadmath.0.dylib {in_pkg}')

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
