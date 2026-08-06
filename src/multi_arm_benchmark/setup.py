from setuptools import find_packages, setup

package_name = "multi_arm_benchmark"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    package_data={"": ["scenarios/*.yaml"]},
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="lenovo",
    maintainer_email="lenovo@todo.todo",
    description="Benchmark system for multi-arm coordination",
    license="Apache-2.0",
    extras_require={
        "test": [
            "pytest",
        ],
    },
    entry_points={
        "console_scripts": [
            "benchmark_node = multi_arm_benchmark.benchmark_node:main",
        ],
    },
)