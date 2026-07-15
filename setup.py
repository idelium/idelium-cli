import os
import sys
from os.path import abspath, dirname, join

from setuptools import find_packages, setup


this_dir = abspath(dirname(__file__))
with open(join(this_dir, 'README.md'), encoding='utf-8') as file:
    long_description = file.read()
def read(rel_path: str) -> str:
    here = os.path.abspath(os.path.dirname(__file__))
    with open(os.path.join(here, rel_path)) as fp:
        return fp.read()


def get_version(rel_path: str) -> str:
    for line in read(rel_path).splitlines():
        if line.startswith("IDELIUM_VERSION"):
            delim = '"' if '"' in line else "'"
            return line.split(delim)[1]
    raise RuntimeError("Unable to find version string.")

setup(
    name='idelium',  # Required
    version=get_version('src/idelium/_internal/main.py'),
    description='Command line Test Automation Tool',  # Optional
    long_description=long_description,
    long_description_content_type="text/markdown",
    author='Idel Fuschini',  # Optional
    author_email='idel.fuschini@gmail.com',  # Optional
    license='MIT',
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Topic :: Software Development :: Build Tools",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3 :: Only",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Programming Language :: Python :: Implementation :: CPython",
        "Programming Language :: Python :: Implementation :: PyPy",
    ],
    url="https://idelium.io/",
    package_dir={"": "src"},

    # You can just specify package directories manually here if your project is
    # simple. Or you can use find_packages().
    #
    # Alternatively, if you just want to distribute a single Python file, use
    # the `py_modules` argument instead as follows, which will expect a file
    # called `my_module.py` to exist:
    #
    #   py_modules=["my_module"],
    #
    package_data={
        "idelium": ["py.typed"],
    },
    packages=find_packages(
        where="src",
        exclude=["contrib", "docs", "tests*", "tasks"],
    ),

    # Specify which Python versions you support. In contrast to the
    # 'Programming Language' classifiers above, 'idelium install' will check this
    # and refuse to install the project if the version does not match. If you
    # do not support Python 2, you can simplify this to '>=3.5' or similar, see
    # https://packaging.python.org/guides/distributing-packages-using-setuptools/#python-requires

    # This field lists other packages that your project depends on to run.
    # Any package you put here will be installed by idelium when your project is
    # installed, so they must be valid existing projects.
    #
    # For an analysis of "install_requires" vs idelium's requirements files see:
    # https://packaging.python.org/en/latest/requirements.html
    install_requires=['selenium>=4.27,<5',
                      'libmagic>=1,<2',
                      'Appium-Python-Client>=4,<6',
                      'webdriver-manager>=4,<5',
                      'Pillow>=10,<13',
                      'requests>=2.32,<3',
                      'requests_hawk>=1.2,<2',
                      'requests_oauthlib>=2,<3',
                      'tqdm>=4.66,<5',
                      ],  # Optional

    # List additional groups of dependencies here (e.g. development
    # dependencies). Users will be able to install these using the "extras"
    # syntax, for example:
    #
    #   $ idelium install sampleproject[dev]
    #
    # Similar to `install_requires` above, these must be valid existing
    # projects.
    extras_require={  # Optional
        'dev': [
            'build>=1.2,<2',
            'check-manifest>=0.50,<1',
            'mypy>=1.10,<2',
            'ruff>=0.11,<1',
        ],
        'test': ['coverage>=7,<8'],
    },
    project_urls={  # Optional
        'Bug Reports': 'https://github.com/idelium/idelium-cli/issues',
        'Project': 'https://idelium.io',
        'Say Thanks!': 'http://www.idelfuschini.it',
        'Source': 'https://github.com/idelium/idelium-cli/',
    },
    entry_points={  # Optional
        'console_scripts': [
            "idelium=idelium._internal.main:main",
        ],
    },
    zip_safe=False,
    python_requires=">=3.10,<3.14",
)
