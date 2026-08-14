from setuptools import setup

package_name = "multi_arm_tools"

setup(
    name=package_name,
    version="0.1.0",
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages",
         ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),

    ],
    install_requires=["setuptools", "pyyaml"],
    zip_safe=True,
    maintainer="MultiArm Team",
    maintainer_email="dev@example.com",
    description="Runtime Developer Experience: robot CLI",
    license="Apache-2.0",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "robot = multi_arm_tools.cli:main",
        ],
    },
)