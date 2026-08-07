from setuptools import setup

package_name = "multi_arm_experience"

setup(
    name=package_name,
    version="0.1.0",
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages",
         ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name + "/launch", [
            "launch/experience.launch.py",
        ]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="MultiArm Team",
    maintainer_email="dev@example.com",
    description="Robot Experience Infrastructure",
    license="Apache-2.0",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "experience_node = multi_arm_experience.experience_node:main",
        ],
    },
)