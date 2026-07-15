"""
Setup para el paquete sifen_py
"""
from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [line.strip() for line in fh if line.strip() and not line.startswith("#")]

setup(
    name="sifen-py",
    version="1.0.0",
    author="SIFEN Paraguay Implementation",
    description="Sistema completo de Facturación Electrónica para SIFEN Paraguay",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/tu-usuario/sifen-py",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.8",
    install_requires=requirements,
    extras_require={
        "dev": [
            "pytest>=8.1.1",
            "pytest-cov>=4.1.0",
            "black>=24.0.0",
            "flake8>=7.0.0",
            "mypy>=1.9.0",
        ],
    },
    include_package_data=True,
    package_data={
        "sifen_py": ["schemas/*.xsd"],
    },
)
