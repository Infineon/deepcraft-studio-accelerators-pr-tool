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
- ``DOMAIN_USE_CASES``: the use-case list is limited again to the selected
  domains, which follow the sensors. A use case is offered when it fits at
  least one selected domain. ``Other``, or an unknown domain, skips this
  filter. When nothing fits both the application and the domain, the domain
  list is shown. An Object Detection project always keeps the Object Detection
  use case, and an Image Classification project always keeps Image Classification.
- ``DOMAIN_IMAGES`` and ``DOMAIN_TAGS``: with no application selected, the
  project-image list is the domain's images. With an application selected, the
  list starts from that application's images and keeps the ones whose tags
  include the domain, and adds the domain's own image (``CANONICAL_DOMAIN_IMAGE``).
  When no application image carries the domain's tags, the application's images
  are kept and the domain's image is added.
  The tags in the prompt are the tags on those images, except tags that belong
  to another domain. The suite image has no domain tag, so a selected domain
  leaves it out.

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

# Domain groups shown first in the sensor list. Other domains follow in catalog
# order, and ``Other`` (sensors without a rule) stays last.
SENSOR_GROUP_ORDER = (
    'Audio',
    'Vision',
    'Motion and Vibration',
    'Electrical Signals',
)


def workflow_for_types(types: list[str]) -> list[str]:
    """Map selected project type(s) to workflow value(s), preserving order."""
    workflows: list[str] = []
    for project_type in types:
        workflow = TYPE_TO_WORKFLOW.get(project_type)
        if workflow and workflow not in workflows:
            workflows.append(workflow)
    return workflows


# Kit families shown in the kit prompt, in this order. A kit whose name does
# not start with one of these is listed under ``Other``.
KIT_GROUP_ORDER = ('PSOC', 'AURIX', 'TRAVEO', 'XENSIV', 'AIROC')


def _kit_family(kit: str) -> str | None:
    text = kit.strip().casefold() if isinstance(kit, str) else ''
    if not text:
        return None
    for family in KIT_GROUP_ORDER:
        if text.startswith(family.casefold()):
            return family
    return None


def kit_groups(kits: list[str]) -> list[tuple[str, list[str]]]:
    """Group *kits* under PSOC, AURIX, TRAVEO, XENSIV, and AIROC.

    The prompt uses the same columns as the sensor list. A kit that does not
    belong to one of those families is listed under ``Other``.
    """
    buckets: dict[str, list[str]] = {}
    other: list[str] = []
    for kit in kits:
        family = _kit_family(kit)
        if family is None:
            other.append(kit)
            continue
        buckets.setdefault(family, []).append(kit)
    groups = [(family, buckets[family]) for family in KIT_GROUP_ORDER if family in buckets]
    if other:
        groups.append(('Other', other))
    return groups


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
    """Group *sensors* under their domain, in ``SENSOR_GROUP_ORDER`` then catalog order.

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
    leading = [domain for domain in SENSOR_GROUP_ORDER if domain in buckets]
    rest = [domain for domain in DOMAIN if domain in buckets and domain not in leading]
    groups = [(domain, buckets[domain]) for domain in leading + rest]
    groups.extend(
        (domain, items) for domain, items in buckets.items()
        if domain not in DOMAIN and domain not in leading
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

# Use cases a domain can actually serve. A use case may fit more than one domain.
# Gesture detection is motion, vision, radar, or touch: a microphone does not offer it.
# ``Other`` is omitted so it skips this filter.
DOMAIN_USE_CASES: dict[str, tuple[str, ...]] = {
    'Audio': (
        'Audio Event Detection', 'Baby Care', 'Baby Cry Detection', 'Breath Detection',
        'Chainsaw Detection', 'Cough Detection', 'Emergency Vehicle Siren Detection',
        'Gunshot Detection', 'Health Care', 'Home Sounds Detection', 'Intrusion Detection',
        'Smart Security Monitoring', 'Sound Event Detection', 'Speech Recognition',
        'Termites Detection', 'Voice Recognition', 'Wake Word Detection',
        'Water Tap Detection',
    ),
    'Vision': (
        'Animal Detection', 'Baby Care', 'Carpet Detection', 'Defect Detection',
        'Driver Assistance', 'Driver Monitoring', 'Entrance Counting',
        'Entry and Exit Detection', 'Face Detection', 'Facial Recognition',
        'Fall Detection', 'Floor Detection', 'Gesture Detection', 'Gestures Detection',
        'Gestures Recognition', 'Ground Detection', 'Hand Movement Type Detection',
        'Health Care', 'Image Classification', 'Image Segmentation', 'Intrusion Detection',
        'Leaf Disease Detection', 'Material Detection', 'Motion Detection',
        'Object Classification', 'Object Detection', 'Obstacle Detection',
        'Occupancy Monitoring', 'People Counting', 'People Detection', 'Person Detection',
        'Person Segmentation', 'Pose Estimation', 'PPE Detection', 'Presence Detection',
        'Rain Drop Classification', 'Road Navigation', 'Road Users Detection',
        'Smart Security Monitoring', 'Surface Detection', 'Termites Detection',
        'Toy Detection', 'Traffic Object Detection', 'Traffic Sign Recognition',
        'Trajectory Control', 'Vehicle Detection', 'Vehicle Tracking', 'Water Detection',
        'Water Tap Detection', 'Weather Classification',
    ),
    'Motion and Vibration': (
        'Anomaly Detection', 'Breath Detection', 'Fall Detection', 'Fault Detection',
        'Gesture Detection', 'Gestures Detection', 'Gestures Recognition',
        'Hand Movement Type Detection', 'Health Care', 'Material Detection',
        'Motion Detection', 'Pose Estimation', 'Predictive Maintenance',
        'Trajectory Control',
    ),
    'Radar': (
        'Breath Detection', 'Driver Assistance', 'Entrance Counting',
        'Entry and Exit Detection', 'Fall Detection', 'Gesture Detection',
        'Gestures Detection', 'Gestures Recognition', 'Intrusion Detection',
        'Motion Detection', 'Object Detection', 'Obstacle Detection',
        'Occupancy Monitoring', 'People Counting', 'People Detection', 'Person Detection',
        'Presence Detection', 'Road Users Detection', 'Smart Security Monitoring',
        'Traffic Object Detection', 'Vehicle Detection', 'Vehicle Tracking',
    ),
    'Touch': (
        'Gesture Detection', 'Gestures Detection', 'Gestures Recognition',
        'Material Detection', 'Touch Detection', 'Water Detection',
    ),
    'Electrical Signals': (
        'Anomaly Detection', 'Arc Fault Detection', 'Capacity Estimation',
        'Fault Detection', 'Predictive Maintenance',
        'State of Charge (SoC) Estimation', 'State of Health (SoH) Estimation',
        'Virtual Winding Temperature Estimation',
    ),
    'Temperature and Humidity': (
        'Anomaly Detection', 'Predictive Maintenance',
        'Virtual Winding Temperature Estimation', 'Weather Classification',
    ),
    'Pressure': (
        'Anomaly Detection', 'Weather Classification',
    ),
    'Gas': (
        'Anomaly Detection', 'Fault Detection',
    ),
}

# deepcraft_ai_suite.webp is listed on every application. It is not in
# DOMAIN_IMAGES, so choosing a domain still leaves it out of a Studio prompt.
SUITE_IMAGE_NAME = 'deepcraft_ai_suite.webp'
APPLICATION_IMAGES: dict[str, tuple[str, ...]] = {
    'ADAS': (
        'automotive_environment.webp', 'automotive_in_cabin.webp', 'city.webp',
        'radar.webp', 'vision.webp', 'deepcraft_ai_suite.webp',
    ),
    'Agriculture and Farming': (
        'animal_monitoring.webp', 'environment_nature_monitoring.webp',
        'deepcraft_ai_suite.webp',
    ),
    'Appliances': (
        'bathroom.webp', 'electrical.webp', 'iot_smart_home.webp',
        'kitchen.webp', 'living_room.webp', 'deepcraft_ai_suite.webp',
    ),
    'Automotive': (
        'audio.webp', 'automotive_environment.webp', 'automotive_in_cabin.webp',
        'automotive_machine_maintenance.webp', 'city.webp', 'radar.webp', 'vision.webp',
        'deepcraft_ai_suite.webp',
    ),
    'Battery Management System (BMS)': (
        'automotive_machine_maintenance.webp', 'electrical.webp', 'deepcraft_ai_suite.webp',
    ),
    'Commercial Building Automation': (
        'city.webp', 'iot_smart_home.webp', 'office.webp',
        'security_monitoring.webp', 'shop_store.webp', 'deepcraft_ai_suite.webp',
    ),
    'Environmental Protection': (
        'animal_monitoring.webp', 'environment_nature_monitoring.webp',
        'deepcraft_ai_suite.webp',
    ),
    'Games': ('hmi.webp', 'motion.webp', 'sport.webp', 'vision.webp', 'deepcraft_ai_suite.webp'),
    'Healthcare': ('audio.webp', 'health.webp', 'wearables.webp', 'deepcraft_ai_suite.webp'),
    'Humanoid Robot': ('hmi.webp', 'motion.webp', 'vision.webp', 'deepcraft_ai_suite.webp'),
    'Industrial IoT': (
        'electrical.webp', 'industrial_assembly_line_hmi.webp',
        'industrial_big_machinery.webp', 'industrial_maintenance.webp',
        'motion.webp', 'workshop.webp', 'deepcraft_ai_suite.webp',
    ),
    'Safety Monitoring': (
        'industrial_maintenance.webp', 'industrial_setting_safety.webp',
        'radar.webp', 'security_monitoring.webp', 'vision.webp', 'work_site_setting.webp',
        'deepcraft_ai_suite.webp',
    ),
    'Smart Home': (
        'audio.webp', 'bathroom.webp', 'bedroom.webp', 'iot_smart_home.webp',
        'kitchen.webp', 'living_room.webp', 'security_monitoring.webp',
        'deepcraft_ai_suite.webp',
    ),
    'Smart Manufacturing': (
        'industrial_assembly_line_hmi.webp', 'industrial_big_machinery.webp',
        'industrial_maintenance.webp', 'industrial_setting_safety.webp',
        'work_site_setting.webp', 'workshop.webp', 'deepcraft_ai_suite.webp',
    ),
    'Wearables': (
        'health.webp', 'motion.webp', 'sport.webp', 'wearables.webp',
        'deepcraft_ai_suite.webp',
    ),
}

# Images whose subject is a sensing domain. With no application selected, these
# are the images offered. The application-then-domain filter lives in
# image_names_for_context and uses DOMAIN_TAGS, not this table, so an
# application image can stay when it carries the domain's tag. An image may
# fit more than one domain. ``Other`` is omitted so it skips this filter.
DOMAIN_IMAGES: dict[str, tuple[str, ...]] = {
    'Audio': ('audio.webp',),
    'Vision': (
        'animal_monitoring.webp', 'hmi.webp', 'security_monitoring.webp', 'vision.webp',
    ),
    'Motion and Vibration': (
        'automotive_machine_maintenance.webp', 'industrial_maintenance.webp',
        'motion.webp', 'sport.webp', 'wearables.webp',
    ),
    'Radar': ('hmi.webp', 'radar.webp', 'security_monitoring.webp'),
    'Touch': ('hmi.webp',),
    'Electrical Signals': (
        'automotive_machine_maintenance.webp', 'electrical.webp',
        'industrial_maintenance.webp',
    ),
    'Temperature and Humidity': ('environment_nature_monitoring.webp',),
    'Pressure': ('environment_nature_monitoring.webp',),
    'Gas': ('environment_nature_monitoring.webp',),
}

# Sensing tags that say an image fits a domain. An application image such as
# automotive_in_cabin.webp stays for Vision because it carries "vision" and
# "camera". Other words on a domain image, such as "monitoring" on vision.webp,
# do not define the domain.
DOMAIN_TAGS: dict[str, tuple[str, ...]] = {
    'Audio': ('audio', 'microphone', 'voice', 'music', 'noise'),
    'Vision': ('vision', 'camera'),
    'Motion and Vibration': (
        'motion', 'vibration', 'accelerometer', 'gyroscope', 'magnetometer',
    ),
    'Radar': ('radar',),
    'Touch': ('touch',),
    'Electrical Signals': ('electronics', 'power', 'voltage', 'current'),
    'Temperature and Humidity': ('temperature', 'humidity'),
    'Pressure': ('pressure',),
    'Gas': ('gas',),
}

# The image offered for a domain alongside the application's own images.
CANONICAL_DOMAIN_IMAGE: dict[str, str] = {
    'Audio': 'audio.webp',
    'Vision': 'vision.webp',
    'Motion and Vibration': 'motion.webp',
    'Radar': 'radar.webp',
    'Touch': 'hmi.webp',
    'Electrical Signals': 'electrical.webp',
    'Temperature and Humidity': 'environment_nature_monitoring.webp',
    'Pressure': 'environment_nature_monitoring.webp',
    'Gas': 'environment_nature_monitoring.webp',
}


def _limited_to_both(
    by_application: list[str] | None,
    by_domain: list[str] | None,
) -> list[str] | None:
    """Intersection of an application list and a domain list.

    ``None`` leaves that side open. When both limit the list and nothing is in
    both, the domain list is returned.
    """
    if by_application is None:
        return by_domain
    if by_domain is None:
        return by_application
    found = set(by_domain)
    overlap = [item for item in by_application if item in found]
    return overlap or by_domain


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


def use_cases_for_domains(domains: list[str]) -> list[str] | None:
    """Use cases for the selected domains, in catalog order.

    ``None`` skips this filter: no domain, ``Other``, or a name that is not in
    ``DOMAIN_USE_CASES``. Several domains combine their use cases.
    """
    keys = _mapped_keys(domains, DOMAIN_USE_CASES)
    if keys is None:
        return None
    found = {use_case for key in keys for use_case in DOMAIN_USE_CASES[key]}
    from metadata.choices import USE_CASE
    return [use_case for use_case in USE_CASE if use_case in found]


def use_case_groups(use_cases: list[str], domains: list[str]) -> list[tuple[str, list[str]]]:
    """Group *use_cases* under the selected domains, in the sensor-column style.

    Each use case is listed once, under the first selected domain that contains
    it. A use case that fits no selected domain is listed under ``Other``.
    When no domain is selected, every catalog domain that contains one of the
    use cases is a heading.
    """
    from metadata.choices import DOMAIN

    offered = set(use_cases)
    if domains:
        headings = [domain for domain in domains if domain in DOMAIN_USE_CASES]
    else:
        headings = [domain for domain in DOMAIN if domain in DOMAIN_USE_CASES]
    placed: set[str] = set()
    groups: list[tuple[str, list[str]]] = []
    for domain in headings:
        items = [
            name for name in DOMAIN_USE_CASES[domain]
            if name in offered and name not in placed
        ]
        if items:
            groups.append((domain, items))
            placed.update(items)
    other = [name for name in use_cases if name not in placed]
    if other:
        groups.append(('Other', other))
    return groups


# The use case that names the vision project. Shown even when the application
# and domain filters would leave it out.
PROJECT_USE_CASE = {
    'Object Detection': 'Object Detection',
    'Image Classification': 'Image Classification',
}


def project_use_case(algorithm: object) -> str | None:
    """The use case an Object Detection or Image Classification project always offers."""
    if isinstance(algorithm, list):
        for item in algorithm:
            found = project_use_case(item)
            if found:
                return found
        return None
    if not isinstance(algorithm, str) or not algorithm.strip():
        return None
    text = algorithm.strip()
    if text in PROJECT_USE_CASE:
        return PROJECT_USE_CASE[text]
    folded = {key.casefold(): value for key, value in PROJECT_USE_CASE.items()}
    return folded.get(text.casefold())


def with_project_use_case(use_cases: list[str] | None, algorithm: object) -> list[str] | None:
    """Add the vision project's own use case when a filter left it out.

    ``None`` stays ``None``: the full list already contains both use cases.
    The added use case keeps its place in the catalog order.
    """
    required = project_use_case(algorithm)
    if use_cases is None or required is None or required in use_cases:
        return use_cases
    from metadata.choices import USE_CASE
    found = set(use_cases)
    found.add(required)
    return [use_case for use_case in USE_CASE if use_case in found]


def use_cases_for_context(applications: list[str], domains: list[str]) -> list[str] | None:
    """Use cases that fit the selected applications and the selected domains.

    Each side limits the list on its own. ``None`` from either side leaves
    that side open. When both limit the list and nothing is in both, the
    domain list is returned so the prompt still matches the sensors.
    """
    return _limited_to_both(
        use_cases_for_applications(applications),
        use_cases_for_domains(domains),
    )


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


def image_names_for_domains(domains: list[str]) -> list[str] | None:
    """Project image file names for the selected domains.

    ``None`` skips this filter, for the same reasons as
    :func:`use_cases_for_domains`. Tags shown in the prompt are the tags of
    these images.
    """
    keys = _mapped_keys(domains, DOMAIN_IMAGES)
    if keys is None:
        return None
    found = {name for key in keys for name in DOMAIN_IMAGES[key]}
    return sorted(found)


def _domain_tag_set(domains: list[str]) -> set[str]:
    """Lower-cased sensing tags for *domains*, or an empty set when the filter is open."""
    keys = _mapped_keys(domains, DOMAIN_TAGS)
    if keys is None:
        return set()
    return {tag.casefold() for key in keys for tag in DOMAIN_TAGS[key]}


def _images_with_domain_tags(names: list[str], domains: list[str]) -> list[str]:
    """Names in *names* that carry a tag of one of *domains*.

    The suite image is left out: its tags name the product, so a selected
    domain removes it from a Studio prompt.
    """
    wanted = _domain_tag_set(domains)
    if not wanted:
        return []
    from image_selector import get_tags_for_images

    kept: list[str] = []
    for name in names:
        if name == SUITE_IMAGE_NAME:
            continue
        tags = {tag.casefold() for tag in get_tags_for_images([name])}
        if tags & wanted:
            kept.append(name)
    return sorted(kept)


def image_list_follows_the_domain(applications: list[str], domains: list[str]) -> bool:
    """True when no application image carries a tag of the selected domains.

    The prompt then adds the domain's own image to the application's images.
    """
    by_application = image_names_for_applications(applications)
    if by_application is None or image_names_for_domains(domains) is None:
        return False
    return not _images_with_domain_tags(by_application, domains)


def _canonical_domain_images(domains: list[str]) -> list[str]:
    """The domain image to suggest for each selected domain."""
    keys = _mapped_keys(domains, CANONICAL_DOMAIN_IMAGE)
    if keys is None:
        return []
    found: list[str] = []
    for key in keys:
        name = CANONICAL_DOMAIN_IMAGE[key]
        if name not in found:
            found.append(name)
    return found


def _other_domain_tags(domains: list[str]) -> set[str]:
    """Sensing tags of every domain except the selected ones."""
    selected = _domain_tag_set(domains)
    if not selected:
        return set()
    every = {tag.casefold() for tags in DOMAIN_TAGS.values() for tag in tags}
    return every - selected


def image_names_for_context(applications: list[str], domains: list[str]) -> list[str] | None:
    """Images for the selected applications, then limited to the selected domains.

    The application list comes first. A selected domain keeps the images in
    that list whose tags include the domain, and adds that domain's own image.
    Automotive with Vision therefore offers ``vision.webp`` and the automotive
    images that carry a vision tag. When no application image carries the
    domain's tags, the application's images are kept and the domain's own image
    is added, so Automotive with Gas offers the automotive images and
    ``environment_nature_monitoring.webp``. A side that leaves the list open
    (see :func:`image_names_for_domains`) is ignored, and the other side is
    returned alone.
    """
    by_application = image_names_for_applications(applications)
    by_domain = image_names_for_domains(domains)
    if by_application is None:
        return by_domain
    if by_domain is None:
        return by_application
    matched = _images_with_domain_tags(by_application, domains)
    if not matched:
        # No application image has the domain's tags: keep the application's
        # images and add the domain's own image.
        matched = [name for name in by_application if name != SUITE_IMAGE_NAME]
    return sorted(set(matched) | set(_canonical_domain_images(domains)))


def tags_for_image_context(names: list[str] | None, domains: list[str]) -> list[str] | None:
    """Tags to offer for *names* once a domain is selected.

    ``None`` keeps every tag on the images. A selected domain keeps the tags
    on the offered images and drops tags that belong to the other domains, so
    Vision keeps ``vision`` and ``camera`` and leaves out ``audio`` and ``radar``.
    """
    if names is None or image_names_for_domains(domains) is None:
        return None
    from image_selector import get_tags_for_images

    blocked = _other_domain_tags(domains)
    return [
        tag for tag in get_tags_for_images(names)
        if tag.casefold() not in blocked
    ]
