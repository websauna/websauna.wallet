import os

from setuptools import setup, find_packages


here = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(here, 'README.rst')) as f:
    README = f.read()
with open(os.path.join(here, 'CHANGES.rst')) as f:
    CHANGES = f.read()


setup(name='websauna.wallet',
      version_format='{tag}.{commitcount}+{gitsha}',
      description='wallet',
      long_description=README + '\n\n' + CHANGES,
      classifiers=[
        "Programming Language :: Python",
        "Framework :: Pyramid",
        "Topic :: Internet :: WWW/HTTP",
        "Topic :: Internet :: WWW/HTTP :: WSGI :: Application",
        ],
      author='Mikko Ohtamaa',
      author_email='mikko@opensourcehacker.com',
      url='https://websauna.org',
      keywords='web websauna pyramid',
      packages=find_packages(),
      include_package_data=True,
      zip_safe=False,
      test_suite='websauna.wallet',
      # automatic version generation for development releases:
      setup_requires=[
          'setuptools-git >= 0',
          'setuptools-git-version',
      ],
      install_requires=['websauna', 'python-redis-lock', 'Markdown'],
      extras_require={
        # Dependencies for running test suite
        'test': ['websauna[test]', 'pexpect'],

        # Dependencies to make releases
        'dev': ['websauna[dev]'],

      },
      # Define where this application starts as referred by WSGI web servers
      entry_points="""\
      [paste.app_factory]
      main = websauna.wallet.demo:main

      [pytest11]
      ethereum=populus.plugin
      wallet-gevent=websauna.wallet.tests.plugin

      [console_scripts]
      ethereum-service = websauna.wallet.ethereum.main:main
      ethereum-service-one-shot= websauna.wallet.ethereum.main:one_shot_main
      wallet-bootstrap = websauna.wallet.bin.bootstrap:main
      ethereum-unlock = websauna.wallet.bin.unlock:main
      ethereum-clear-service-locks = websauna.wallet.bin.clearlocks:main
      """,
      )
