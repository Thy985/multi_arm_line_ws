from setuptools import setup

package_name = "multi_arm_runtime_api"

setup(
    name=package_name,
    version="0.1.0",
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages",
         ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name + "/launch", [
            "launch/runtime_api.launch.py",
            "launch/led_status.launch.py",
        ]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="MultiArm Team",
    maintainer_email="dev@example.com",
    description="Robot Runtime API",
    license="Apache-2.0",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "runtime_api_node = multi_arm_runtime_api.runtime_api_node:main",
            "led_status_node = multi_arm_runtime_api.led_status_node:main",
        ],
    },
)