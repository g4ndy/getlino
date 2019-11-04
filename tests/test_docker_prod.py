from os.path import dirname, join
from atelier.test import TestCase
import getlino

class DockerTests(TestCase):
    Docker_Command = 'docker run prod_debian /bin/bash -c '.split()
    def test_prod_debian(self):
        #self.run_subprocess('docker build -t prod_debian -f docker/prod/Dockerfile .'.split())
        self.run_subprocess(Docker_Command.append('cd /usr/local/lino/lino_local/mysite1 && ls -l'))
        self.run_subprocess(Docker_Command.append('cd /usr/local/lino/lino_local/mysite1 && ./pull.sh '))
        self.run_subprocess(Docker_Command.append('cd /usr/local/lino/lino_local/mysite1 && ./make_snapshot.sh '))
        self.run_subprocess(Docker_Command.append('. /usr/local/lino/lino_local/mysite1/env/bin/activate && cd /usr/local/lino/lino_local/mysite1 && exec python manage.py runserver '))
        self.run_subprocess(Docker_Command.append('. /usr/local/lino/lino_local/mysite1/env/bin/activate && cd /usr/local/lino/lino_local/mysite1 && exec python manage.py runserver'))

    def test_prod_ubuntu(self):
        #self.run_subprocess('docker build -t prod_debian -f docker/prod/Dockerfile_ubuntu .'.split())
        self.run_subprocess('docker run prod_ubuntu ls -l'.split())
        self.run_subprocess("docker run prod_ubuntu /bin/bash -c 'cd /usr/local/lino/lino_local/mysite1 && ./pull.sh '".split())
        self.run_subprocess("docker run prod_debian /bin/bash -c 'cd /usr/local/lino/lino_local/mysite1 && ./make_snapshot.sh '".split())
        self.run_subprocess("docker run prod_ubuntu /bin/bash -c 'cd /usr/local/lino/lino_local/mysite1 && ls -l'".split())
        self.run_subprocess("docker run prod_ubuntu /bin/bash -c '. /usr/local/lino/lino_local/mysite1/env/bin/activate && cd /usr/local/lino/lino_local/mysite1 && exec python manage.py runserver '".split())
