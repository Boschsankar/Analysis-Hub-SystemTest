#!/usr/bin/env python3
"""
Smart Meter Analysis Tools - Setup Configuration
Package for analyzing smart meter data with Streamlit.
"""

from setuptools import setup, find_packages
import os

# Read the README file
def read_file(filename):
    """Read file contents."""
    filepath = os.path.join(os.path.dirname(__file__), filename)
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    return ""


# Read the requirements file
def read_requirements(filename='requirements.txt'):
    """Read requirements from file."""
    filepath = os.path.join(os.path.dirname(__file__), filename)
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip() and not line.startswith('#')]
    return []


setup(
    name='smartmeter-analysis-tools',
    version='1.0.0',
    author='Bosch Group',
    author_email='support@bosch.com',
    description='Comprehensive Smart Meter Data Analysis Suite',
    long_description=read_file('README.md'),
    long_description_content_type='text/markdown',
    url='https://github.com/bosch/smartmeter-analysis-tools',
    license='Proprietary',
    
    # Package discovery
    packages=find_packages(include=['_pages*', 'utils*']),
    include_package_data=True,
    
    # Python version requirement
    python_requires='>=3.8',
    
    # Core dependencies
    install_requires=read_requirements(),
    
    # Optional dependencies for Windows
    extras_require={
        'windows': [
            'pywin32>=311',  # For Outlook email functionality
        ],
        'dev': [
            'pytest>=6.0.0',
            'pytest-cov>=2.0.0',
            'black>=21.0.0',
            'flake8>=3.9.0',
            'mypy>=0.900',
        ],
        'docs': [
            'sphinx>=4.0.0',
            'sphinx-rtd-theme>=1.0.0',
        ],
    },
    
    # Entry points
    entry_points={
        'console_scripts': [
            'smartmeter=Home:main',
        ],
    },
    
    # Metadata
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'Intended Audience :: System Administrators',
        'License :: Other/Proprietary License',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Topic :: Scientific/Engineering :: Information Analysis',
        'Topic :: Utilities',
    ],
    
    keywords=[
        'smart-meter',
        'data-analysis',
        'streamlit',
        'meter-readings',
        'iot',
    ],
    
    project_urls={
        'Documentation': 'https://github.com/bosch/smartmeter-analysis-tools/wiki',
        'Source Code': 'https://github.com/bosch/smartmeter-analysis-tools',
        'Bug Tracker': 'https://github.com/bosch/smartmeter-analysis-tools/issues',
    },
)
