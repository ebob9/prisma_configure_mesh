from setuptools import setup

with open('README.md') as f:
    long_description = f.read()

setup(name='prisma_configure_mesh',
      version='1.0.0b1',
      description='Utility for changing from Hub/Spoke to Partial or Full Mesh for Prisma SD-WAN.',
      long_description=long_description,
      long_description_content_type='text/markdown',
      url='https://github.com/ebob9/prisma_configure_mesh',
      author='Aaron Edwards',
      author_email='prisma_configure_mesh@ebob9.com',
      license='MIT',
      install_requires=[
            'cloudgenix >= 5.5.1b2',
            'progressbar2 >= 3.53.1'
      ],
      packages=['prisma_mesh_functions'],
      entry_points={
            'console_scripts': [
                  'prisma_configure_mesh = prisma_mesh_functions:go'
                  ]
      },
      classifiers=[
            "Development Status :: 4 - Beta",
            "Intended Audience :: Developers",
            "License :: OSI Approved :: MIT License",
            "Programming Language :: Python :: 3.7",
            "Programming Language :: Python :: 3.8",
            "Programming Language :: Python :: 3.9",
            "Programming Language :: Python :: 3.10",
      ]
      )
