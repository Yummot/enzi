import os
from setuptools import setup

setup(
    name="enzi",
    # use_scm_version={
    #     "relative_to": __file__,
    #     "write_to": "enzi/version.py",
    # },
    version="0.1.6",
    author="Mot Yu",
    author_email="mot.yu@outlook.com",
    license="MIT",
    packages=['enzi'],
    package_data={
        'enzi': [
            "enzi/backend/templates/*"
        ]
    },
    description="Enzi(Enzyme IC) is a tool for automating HDL project",
    entry_points={
        'console_scripts': [
            'enzi = enzi.main:main'
        ]
    },
    python_requires='>=3.6',
    install_requires=[
        'toml>=0.10.0',
        'semver>=2.8',
        'jinja2>=2.0.0'
    ],
    extras_require={
        'color_log': ['coloredlogs>=10.0', ]
    }
)
