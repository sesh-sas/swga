from distutils.core import setup

setup(
    name='PrimerSets',
    version='0.1.0',
    author='Erik Clarke',
    author_email='ecl@mail.med.upenn.edu',
    packages=['swga'],
    scripts=['bin/set_finder'],
    url='https://github.com/BrissonEEDS/PrimerSets',
    license='LICENSE.txt',
    description='Pipeline to select compatible primer sets for selective whole-genome amplification.',
    long_description=open('README.md').read(),
    install_requires=[
        "numpy > 1.6.1"
    ],
)
    
    
