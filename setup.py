from setuptools import setup, find_packages

setup(
    name="dex",
    version="0.1.2",
    packages=find_packages(),
    package_data={
        "dex": ["abis/*.json"],
    },
    include_package_data=True,
    install_requires=[
        "pytz>=2023.3.post1",
        "mmh3>=4.0.1",
        "web3>=7.7.0",
        "requests>=2.32.3",
        "pycryptodome>=3.21.0",
        "websockets>=12.0",
        "parsimonious>=0.9.0",
        "python-dotenv>=1.0.0",
        "pandas>=2.2.3"
    ],
    python_requires=">=3.8",
    description="DEX interaction library for Base network",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12"
    ],
)
