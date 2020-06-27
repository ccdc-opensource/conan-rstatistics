from conans import ConanFile


class TestPackage(ConanFile):
    
    def test(self):
        self.run("R -e 'q()'")