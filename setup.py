import os
from setuptools import setup

setup(
    name="enzi",
    version="0.8.1",
    author="Mot Yu",
    author_email="mot.yu@outlook.com",
    url="https://github.com/Yummot/enzi",
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
        'jinja2>=2.0.0',
        'colorama>=0.4.0',
        'coloredlogs>=9.3'
        'pytest>=5.0.1',
        'ordered-set>=3.1.1',
        'networkx>=2.0',
    ],
)
