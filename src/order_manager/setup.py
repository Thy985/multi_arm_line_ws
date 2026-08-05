from setuptools import find_packages, setup

package_name = 'order_manager'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='lenovo',
    maintainer_email='lenovo@todo.todo',
    description='TODO: Package description',
    license='TODO: License declaration',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            'enhanced_multi_arm_coordinator = order_manager.nodes.multi_arm_coordinator:main',
            'multi_arm_coordinator = order_manager.nodes.multi_arm_coordinator:main',
            'test_arm_control = order_manager.nodes.test_arm_control:main',
            'diagnostics_monitor = order_manager.nodes.diagnostics_monitor:main',
        ],
    },
)
