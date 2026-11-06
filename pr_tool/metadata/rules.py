"""Autoselection rules that fill or limit one metadata field from another.

Add a rule by extending the mapping next to the others. Collection applies
these functions while prompting, and again when metadata is finalized.

- ``TYPE_TO_WORKFLOW``: each project type sets its workflow.
- ``KIT_TO_DEVICE``: known kits set the device. One unknown kit leaves device open.
- ``SENSOR_TO_DOMAIN``: each listed sensor belongs to one domain. Every domain
  those sensors map to is selected, with no prompt. A sensor with no entry
  (``Other``, or a custom name) leaves the full domain list open.
- ``APPLICATION_USE_CASES`` and ``APPLICATION_IMAGES``: the use-case list and
  the project-image list (names, and the tags on those images) are limited to
  the selected application. ``Other``, or an unknown application, keeps the
  full lists.

Vision Studio projects still fill sensors and kits from the ``.improj``
algorithm in ``metadata.improj``. Domain then follows the sensor rule.
"""

from __future__ import annotations

TYPE_TO_WORKFLOW = {
    'Model Development': 'ML Development',
    'Model Deployment': 'ML Deployment',
}

# Each known kit maps to exactly one device.
KIT_TO_DEVICE: dict[str, str] = {
    'AURIX\u2122 KIT_A2G_TC375_LITE': 'AURIX\u2122 TC3x',
    'AURIX\u2122 KIT_A3G_TC4D7_LITE': 'AURIX\u2122 TC4x',
    'AURIX\u2122 TC4x STD Triboard': 'AURIX\u2122 TC4x',
    'TRAVEO\u2122 T2G Body EntryLite Kit KIT_T2G-B-E_LITE': 'TRAVEO\u2122 T2G body entry',
    'XENSIV\u2122 KIT_CSK_BGT60TR13C': 'XENSIV\u2122 Radar BGT60TR13C',
    'PSOC\u2122 4100S Max Pioneer Kit': 'PSOC\u2122 4',
    'PSOC\u2122 6 AI Kit': 'PSOC\u2122 6',
    'PSOC\u2122 6 Pioneer Kit': 'PSOC\u2122 6',
    'PSOC\u2122 C3 Motor Control Kit': 'PSOC\u2122 C3',
    'PSOC\u2122 Edge AI Kit': 'PSOC\u2122 Edge',
    'PSOC\u2122 Edge Eval Kit': 'PSOC\u2122 Edge',
    'AIROC\u2122 UWB TSL100 Engineering Sample Kit': 'AIROC\u2122 UWB TSL100',
    'XENSIV\u2122 TLE493D-W2B6 MS2GO': 'XENSIV\u2122 TLE493D',
}

# One line per sensor. Sensors that share a domain stay on that domain together.
# ``Other`` is omitted on purpose: it does not force a domain, so the user
# picks one from the full list.
SENSOR_TO_DOMAIN: dict[str, str] = {
    'Microphone': 'Audio',
    'Camera': 'Vision',
    'TOF Camera': 'Vision',
    'IMU': 'Motion and Vibration',
    'Accelerometer': 'Motion and Vibration',
    'Gyroscope': 'Motion and Vibration',
    'Magnetometer': 'Motion and Vibration',
    'Hall Sensor': 'Motion and Vibration',
    'Vibration': 'Motion and Vibration',
    # Listed with torque, RPM, and speed, so treated as rotational motion.
    'Torque': 'Motion and Vibration',
    'RPM': 'Motion and Vibration',
    'Speed': 'Motion and Vibration',
    'Radar': 'Radar',
    # Ranging and presence sensing. No other domain fits.
    'UWB': 'Radar',
    'WiFi': 'Radar',
    'Bluetooth': 'Radar',
    'Capacitive Sensing': 'Touch',
    'Inductive Sensing': 'Touch',
    'Current': 'Electrical Signals',
    'Voltage': 'Electrical Signals',
    'Power': 'Electrical Signals',
    'Temperature': 'Temperature and Humidity',
    'Humidity': 'Temperature and Humidity',
    'Pressure': 'Pressure',
    # XENSIV DPS310 / DPS368 are digital barometric pressure sensors.
    'DPS': 'Pressure',
    'Gas': 'Gas',
}

_SENSOR_DOMAIN_FOLDED = {
    sensor.casefold(): domain for sensor, domain in SENSOR_TO_DOMAIN.items()
}


def workflow_for_types(types: list[str]) -> list[str]:
    """Map selected project type(s) to workflow value(s), preserving order."""
    workflows: list[str] = []
    for project_type in types:
        workflow = TYPE_TO_WORKFLOW.get(project_type)
        if workflow and workflow not in workflows:
            workflows.append(workflow)
    return workflows


def devices_for_kits(kits: list[str]) -> list[str] | None:
    """Return devices for known kits; ``None`` when any kit is custom."""
    devices: list[str] = []
    for kit in kits:
        device = KIT_TO_DEVICE.get(kit)
        if device is None:
            return None
        if device not in devices:
            devices.append(device)
    return devices


def _domain_for_sensor(sensor: str) -> str | None:
    if not isinstance(sensor, str):
        return None
    text = sensor.strip()
    if not text:
        return None
    return SENSOR_TO_DOMAIN.get(text) or _SENSOR_DOMAIN_FOLDED.get(text.casefold())


def sensor_groups(sensors: list[str]) -> list[tuple[str, list[str]]]:
    """Group *sensors* under their domain, in catalog domain order.

    A sensor with no domain rule is listed under ``Other``.
    """
    from metadata.choices import DOMAIN
    buckets: dict[str, list[str]] = {}
    other: list[str] = []
    for sensor in sensors:
        domain = _domain_for_sensor(sensor)
        if domain is None:
            other.append(sensor)
            continue
        buckets.setdefault(domain, []).append(sensor)
    groups = [(domain, buckets[domain]) for domain in DOMAIN if domain in buckets]
    groups.extend(
        (domain, items) for domain, items in buckets.items() if domain not in DOMAIN
    )
    if other:
        groups.append(('Other', other))
    return groups


def domains_for_sensors(sensors: list[str]) -> list[str] | None:
    """Domains the selected sensors allow.

    ``None`` leaves domain open: there are no sensors, or at least one sensor
    has no domain rule. Otherwise every matching domain is returned in catalog
    order and selected automatically.
    """
    if not sensors:
        return None
    found: set[str] = set()
    for sensor in sensors:
        domain = _domain_for_sensor(sensor)
        if domain is None:
            return None
        found.add(domain)
    from metadata.choices import DOMAIN
    ordered = [domain for domain in DOMAIN if domain in found]
    ordered.extend(sorted(domain for domain in found if domain not in ordered))
    return ordered


# Use cases and project images that fit each application. A value may be listed
# under more than one application. ``Other`` is omitted so it keeps both full lists.
APPLICATION_USE_CASES: dict[str, tuple[str, ...]] = {
    'ADAS': (
        'Driver Assistance', 'Driver Monitoring', 'Emergency Vehicle Siren Detection',
        'Face Detection', 'Facial Recognition', 'Ground Detection', 'Image Classification',
        'Image Segmentation', 'Object Classification', 'Object Detection', 'Obstacle Detection',
        'People Detection', 'Person Detection', 'Person Segmentation', 'Rain Drop Classification',
        'Road Navigation', 'Road Users Detection', 'Traffic Object Detection',
        'Traffic Sign Recognition', 'Trajectory Control', 'Vehicle Detection',
        'Vehicle Tracking', 'Weather Classification',
    ),
    'Agriculture and Farming': (
        'Animal Detection', 'Chainsaw Detection', 'Ground Detection', 'Image Classification',
        'Image Segmentation', 'Leaf Disease Detection', 'Surface Detection',
        'Termites Detection', 'Water Detection', 'Weather Classification',
    ),
    'Appliances': (
        'Audio Event Detection', 'Carpet Detection', 'Floor Detection', 'Gesture Detection',
        'Gestures Detection', 'Gestures Recognition', 'Home Sounds Detection',
        'Material Detection', 'Sound Event Detection', 'Touch Detection',
        'Water Detection', 'Water Tap Detection',
    ),
    'Automotive': (
        'Arc Fault Detection', 'Audio Event Detection', 'Breath Detection',
        'Driver Assistance', 'Driver Monitoring', 'Emergency Vehicle Siren Detection',
        'Face Detection', 'Facial Recognition', 'Object Detection', 'Obstacle Detection',
        'Occupancy Monitoring', 'People Counting', 'People Detection', 'Person Detection',
        'Person Segmentation', 'Predictive Maintenance', 'Presence Detection',
        'Rain Drop Classification', 'Road Navigation', 'Road Users Detection',
        'Sound Event Detection', 'Speech Recognition', 'Traffic Object Detection',
        'Traffic Sign Recognition', 'Trajectory Control', 'Vehicle Detection',
        'Vehicle Tracking', 'Voice Recognition', 'Wake Word Detection', 'Weather Classification',
    ),
    'Battery Management System (BMS)': (
        'Anomaly Detection', 'Arc Fault Detection', 'Capacity Estimation', 'Fault Detection',
        'State of Charge (SoC) Estimation', 'State of Health (SoH) Estimation',
        'Virtual Winding Temperature Estimation',
    ),
    'Commercial Building Automation': (
        'Entrance Counting', 'Entry and Exit Detection', 'Intrusion Detection',
        'Motion Detection', 'Occupancy Monitoring', 'People Counting', 'Presence Detection',
        'Smart Security Monitoring', 'Touch Detection',
    ),
    'Environmental Protection': (
        'Animal Detection', 'Chainsaw Detection', 'Leaf Disease Detection',
        'Termites Detection', 'Water Detection', 'Weather Classification',
    ),
    'Games': (
        'Gesture Detection', 'Gestures Detection', 'Gestures Recognition',
        'Hand Movement Type Detection', 'Motion Detection', 'Pose Estimation',
        'Speech Recognition', 'Touch Detection', 'Toy Detection', 'Voice Recognition',
    ),
    'Healthcare': (
        'Baby Care', 'Baby Cry Detection', 'Breath Detection', 'Cough Detection',
        'Face Detection', 'Facial Recognition', 'Fall Detection', 'Health Care',
        'Pose Estimation',
    ),
    'Humanoid Robot': (
        'Floor Detection', 'Gesture Detection', 'Gestures Detection', 'Gestures Recognition',
        'Ground Detection', 'Hand Movement Type Detection', 'Object Detection',
        'Obstacle Detection', 'People Detection', 'Person Detection', 'Pose Estimation',
        'Speech Recognition', 'Surface Detection', 'Touch Detection', 'Trajectory Control',
        'Voice Recognition', 'Wake Word Detection',
    ),
    'Industrial IoT': (
        'Anomaly Detection', 'Arc Fault Detection', 'Capacity Estimation', 'Defect Detection',
        'Fault Detection', 'Material Detection', 'Object Classification',
        'Predictive Maintenance', 'Virtual Winding Temperature Estimation',
    ),
    'Safety Monitoring': (
        'Audio Event Detection', 'Chainsaw Detection', 'Cough Detection',
        'Emergency Vehicle Siren Detection', 'Entrance Counting', 'Entry and Exit Detection',
        'Fall Detection', 'Gunshot Detection', 'Image Classification', 'Intrusion Detection',
        'Motion Detection', 'Object Detection', 'Occupancy Monitoring', 'People Counting',
        'People Detection', 'Person Detection', 'Person Segmentation', 'PPE Detection',
        'Presence Detection', 'Smart Security Monitoring', 'Sound Event Detection',
    ),
    'Smart Home': (
        'Audio Event Detection', 'Baby Care', 'Baby Cry Detection', 'Carpet Detection',
        'Entrance Counting', 'Entry and Exit Detection', 'Fall Detection',
        'Gesture Detection', 'Gestures Detection', 'Gestures Recognition',
        'Home Sounds Detection', 'Intrusion Detection', 'Motion Detection',
        'Occupancy Monitoring', 'People Counting', 'People Detection', 'Person Detection',
        'Presence Detection', 'Smart Security Monitoring', 'Sound Event Detection',
        'Speech Recognition', 'Touch Detection', 'Toy Detection', 'Voice Recognition',
        'Wake Word Detection', 'Water Detection', 'Water Tap Detection',
    ),
    'Smart Manufacturing': (
        'Anomaly Detection', 'Defect Detection', 'Fault Detection', 'Image Classification',
        'Image Segmentation', 'Material Detection', 'Object Classification',
        'Object Detection', 'Person Detection', 'PPE Detection', 'Predictive Maintenance',
        'Surface Detection',
    ),
    'Wearables': (
        'Breath Detection', 'Cough Detection', 'Fall Detection', 'Gesture Detection',
        'Hand Movement Type Detection', 'Health Care', 'Motion Detection', 'Pose Estimation',
    ),
}

APPLICATION_IMAGES: dict[str, tuple[str, ...]] = {
    'ADAS': (
        'automotive_environment.webp', 'automotive_in_cabin.webp', 'city.webp',
        'radar.webp', 'vision.webp',
    ),
    'Agriculture and Farming': (
        'animal_monitoring.webp', 'environment_nature_monitoring.webp',
    ),
    'Appliances': (
        'bathroom.webp', 'electrical.webp', 'iot_smart_home.webp',
        'kitchen.webp', 'living_room.webp',
    ),
    'Automotive': (
        'audio.webp', 'automotive_environment.webp', 'automotive_in_cabin.webp',
        'automotive_machine_maintenance.webp', 'city.webp', 'radar.webp', 'vision.webp',
    ),
    'Battery Management System (BMS)': ('electrical.webp',),
    'Commercial Building Automation': (
        'city.webp', 'iot_smart_home.webp', 'office.webp',
        'security_monitoring.webp', 'shop_store.webp',
    ),
    'Environmental Protection': (
        'animal_monitoring.webp', 'environment_nature_monitoring.webp',
    ),
    'Games': ('hmi.webp', 'motion.webp', 'sport.webp', 'vision.webp'),
    'Healthcare': ('audio.webp', 'health.webp', 'wearables.webp'),
    'Humanoid Robot': ('hmi.webp', 'motion.webp', 'vision.webp'),
    'Industrial IoT': (
        'electrical.webp', 'industrial_assembly_line_hmi.webp',
        'industrial_big_machinery.webp', 'industrial_maintenance.webp',
        'motion.webp', 'workshop.webp',
    ),
    'Safety Monitoring': (
        'industrial_maintenance.webp', 'industrial_setting_safety.webp',
        'radar.webp', 'security_monitoring.webp', 'vision.webp', 'work_site_setting.webp',
    ),
    'Smart Home': (
        'audio.webp', 'bathroom.webp', 'bedroom.webp', 'iot_smart_home.webp',
        'kitchen.webp', 'living_room.webp', 'security_monitoring.webp',
    ),
    'Smart Manufacturing': (
        'industrial_assembly_line_hmi.webp', 'industrial_big_machinery.webp',
        'industrial_maintenance.webp', 'industrial_setting_safety.webp',
        'work_site_setting.webp', 'workshop.webp',
    ),
    'Wearables': ('health.webp', 'motion.webp', 'sport.webp', 'wearables.webp'),
}


def _mapped_keys(selected: list[str], table: dict[str, tuple[str, ...]]) -> list[str] | None:
    """Catalog keys for *selected*, or ``None`` when the full list should stay open."""
    if not selected:
        return None
    folded = {key.casefold(): key for key in table}
    keys: list[str] = []
    for item in selected:
        if not isinstance(item, str) or not item.strip():
            return None
        text = item.strip()
        key = text if text in table else folded.get(text.casefold())
        if key is None:
            return None
        if key not in keys:
            keys.append(key)
    return keys


def use_cases_for_applications(applications: list[str]) -> list[str] | None:
    """Use cases for the selected applications, in catalog order.

    ``None`` leaves the full use-case list open: no application, ``Other``, or
    a name that is not in ``APPLICATION_USE_CASES``.
    """
    keys = _mapped_keys(applications, APPLICATION_USE_CASES)
    if keys is None:
        return None
    found = {use_case for key in keys for use_case in APPLICATION_USE_CASES[key]}
    from metadata.choices import USE_CASE
    return [use_case for use_case in USE_CASE if use_case in found]


def image_names_for_applications(applications: list[str]) -> list[str] | None:
    """Project image file names for the selected applications.

    ``None`` leaves the full image catalog open, for the same reasons as
    :func:`use_cases_for_applications`. Tags shown in the prompt are the tags
    of these images.
    """
    keys = _mapped_keys(applications, APPLICATION_IMAGES)
    if keys is None:
        return None
    found = {name for key in keys for name in APPLICATION_IMAGES[key]}
    return sorted(found)
