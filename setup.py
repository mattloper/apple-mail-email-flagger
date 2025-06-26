from setuptools import setup, find_packages

setup(
    name="email-flagger",
    version="1.0.0",
    description="AI-powered email prioritization for Apple Mail",
    author="Your Name",
    author_email="your.email@example.com",
    url="https://github.com/yourusername/email-flagger",
    packages=find_packages(),
    install_requires=[
        "requests>=2.25.1",
    ],
    entry_points={
        "console_scripts": [
            "email-flagger=email_flagger.cli:main",
            "email-flagger-classify=email_flagger.classifier:main",
        ],
    },
    python_requires=">=3.7",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Operating System :: MacOS",
    ],
    include_package_data=True,
    package_data={
        "email_flagger": ["templates/*.applescript"],
    },
)