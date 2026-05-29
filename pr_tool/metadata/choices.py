"""Suggested values for metadata fields.

Domain, application, use case, kit, device, and brand lists are derived from
the DEEPCRAFT AI Hub catalog (``https://deepcraft.infineon.com/master.json``).
Choosing a **brand** sets ``brand_image_id`` and ``brand_url`` together.
Re-run ``scripts/parse_master_json.py`` to refresh when the hub is updated.
"""

from dataclasses import dataclass

ALGORITHM = ('Classification', 'Regression', 'Object Detection')

SENSORS = (
    'Microphone',
    'Camera',
    'IMU',
    'Vibration',
    'Radar',
    'Capacitive Sensing',
    'Inductive Sensing',
    'Current',
    'Voltage',
    'Power',
    'Torque',
    'RPM',
    'DPS',
    'Other',
)

DOMAIN = (
    'Audio',
    'Electronic Sensing',
    'Motion',
    'Radar',
    'Sensing',
    'Touch',
    'Vibration',
    'Vision',
    'Voice',
)

APPLICATION = (
    'ADAS',
    'Alarm & Security',
    'Appliances',
    'AR Devices / Smart Glasses',
    'Audio & Speaker',
    'Automotive',
    'Baby Monitor',
    'Battery Management System (BMS)',
    'Clinical & Hospital Equipment',
    'Collaborative Robot (cobot)',
    'Commercial Building Automation',
    'Commercial, Residential and Industrial Lighting',
    'Domestic Robot',
    'Drone & Multicopter',
    'Embedded Systems',
    'Energy Management',
    'Environmental Protection',
    'Forest Monitoring',
    'Games',
    'Healthcare',
    'Healthcare Wearable & Consumable',
    'Home Health Monitoring',
    'Humanoid Robot',
    'Industrial Automation',
    'Industrial IoT',
    'Industrial Sensor System',
    'Occupancy Monitoring',
    'Predictive Maintenance',
    'Residential Aircon',
    'Safety Monitoring',
    'Security Camera & Video Doorbell',
    'Security Systems',
    'Smart Building',
    'Smart Forest/Environment',
    'Smart Home',
    'Smart Manufacturing',
    'Smart Thermostat',
    'Smart Watch & Wristband',
    'Trajectory Control',
    'Vehicles',
    'Wearables',
)

USE_CASE = (
    'Animal Detection',
    'Anomaly Detection',
    'Audio Event Detection',
    'Baby Care',
    'Baby Cry Detection',
    'Capacity Estimation',
    'Carpet Detection',
    'Chainsaw Detection',
    'Cough Detection',
    'Emergency Vehicle Siren Detection',
    'Entrance Counting',
    'Entry and Exit Detection',
    'Face Detection',
    'Facial Recognition',
    'Fall Detection',
    'Fault Detection',
    'Floor Detection',
    'Gesture Detection',
    'Gestures Detection',
    'Gestures Recognition',
    'Gunshot Detection',
    'Hand Movement Type Detection',
    'Home Sounds Detection',
    'Image Segmentation',
    'Intrusion Detection',
    'Material Detection',
    'Motion Detection',
    'Object Classification',
    'Object Detection',
    'Obstacle Detection',
    'Occupancy Monitoring',
    'People Counting',
    'People Detection',
    'Person Detection',
    'Person Segmentation',
    'Pose Estimation',
    'Predictive Maintenance',
    'Presence Detection',
    'Road Users Detection',
    'Smart Security Monitoring',
    'Sound Event Detection',
    'Speech Recognition',
    'State of Charge (SoC) Estimation',
    'State of Health (SoH) Estimation',
    'Surface Detection',
    'Termites Detection',
    'Touch Detection',
    'Toy Detection',
    'Traffic Object Detection',
    'Trajectory Control',
    'Voice Recognition',
    'Wake Word Detection',
    'Water Detection',
    'Water Tap Detection',
    'Weather Classification',
)

KIT = (
    'AURIX\u2122 KIT_A2G_TC375_LITE',
    'AURIX\u2122 KIT_A3G_TC4D7_LITE',
    'AURIX\u2122 TC4x STD Triboard',
    'KIT_CSK_BGT60TR13C',
    'PSOC\u2122 4100S Max Pioneer Kit',
    'PSOC\u2122 6 AI Kit',
    'PSOC\u2122 6 Pioneer Kit',
    'PSOC\u2122 C3 Motor Control Kit',
    'PSOC\u2122 Edge AI Kit',
    'PSOC\u2122 Edge Eval Kit',
)

DEVICE = (
    'AURIX\u2122 TC3x',
    'AURIX\u2122 TC4x',
    'BGT60TR13C',
    'PSOC\u2122 4',
    'PSOC\u2122 6',
    'PSOC\u2122 C3',
    'PSOC\u2122 Edge',
)

PROJECT_TYPE = ('Model Development', 'Model Deployment')

WORKFLOW = ('ML Development', 'ML Deployment')

TYPE_TO_WORKFLOW = {
    'Model Development': 'ML Development',
    'Model Deployment': 'ML Deployment',
}

# Each known kit maps to exactly one device (derived during metadata collection).
KIT_TO_DEVICE: dict[str, str] = {
    'AURIX\u2122 KIT_A2G_TC375_LITE': 'AURIX\u2122 TC3x',
    'AURIX\u2122 KIT_A3G_TC4D7_LITE': 'AURIX\u2122 TC4x',
    'AURIX\u2122 TC4x STD Triboard': 'AURIX\u2122 TC4x',
    'KIT_CSK_BGT60TR13C': 'BGT60TR13C',
    'PSOC\u2122 4100S Max Pioneer Kit': 'PSOC\u2122 4',
    'PSOC\u2122 6 AI Kit': 'PSOC\u2122 6',
    'PSOC\u2122 6 Pioneer Kit': 'PSOC\u2122 6',
    'PSOC\u2122 C3 Motor Control Kit': 'PSOC\u2122 C3',
    'PSOC\u2122 Edge AI Kit': 'PSOC\u2122 Edge',
    'PSOC\u2122 Edge Eval Kit': 'PSOC\u2122 Edge',
}


def normalize_project_types(value: str | list[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    return [item for item in value if isinstance(item, str) and item.strip()]


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

# Predefined metric labels for model-zoo-psoc metadata.json (values are prompted).
METRIC_LABELS = (
    'Inference Time (ms)',
    'Model Weight (MB)',
    'Input Layer',
    'Output Layer',
    'Compute (MC)',
    'Energy (mJ)',
    'Scratch Pad Size (MB)',
)

@dataclass(frozen=True)
class Brand:
    label: str
    brand_image_id: str
    brand_url: str


INFINEON_BRAND = Brand(
    label='DEEPCRAFT\u2122',
    brand_image_id='deepcraft.webp',
    brand_url=(
        'https://www.infineon.com/design-resources/embedded-software/'
        'deepcraft-edge-ai-solutions'
    ),
)

PARTNER_BRANDS = (
    Brand(
        label='Embedur',
        brand_image_id='embedur.webp',
        brand_url=(
            'https://www.embedur.ai/?utm_source=infineon_site'
            '&utm_medium=referral&utm_campaign=promotion'
        ),
    ),
    Brand(
        label='WG Tech',
        brand_image_id='wgtech-trademark-logo-final-April2024.webp',
        brand_url='https://www.wgtech.ai/',
    ),
)

NEW_BRAND_PARTNER_LABEL = 'New Brand/Partner'

ALL_BRANDS = (INFINEON_BRAND,) + PARTNER_BRANDS
BRANDS_BY_LABEL = {brand.label: brand for brand in ALL_BRANDS}
BRANDS_BY_IMAGE = {brand.brand_image_id: brand for brand in ALL_BRANDS}

INFINEON_BRAND_IMAGE_ID = (INFINEON_BRAND.brand_image_id,)
PARTNER_BRAND_IMAGE_ID = tuple(brand.brand_image_id for brand in PARTNER_BRANDS)
BRAND_IMAGE_ID = INFINEON_BRAND_IMAGE_ID + PARTNER_BRAND_IMAGE_ID

INFINEON_BRAND_URL = INFINEON_BRAND.brand_url
PARTNER_BRAND_URL = tuple(brand.brand_url for brand in PARTNER_BRANDS)
BRAND_URL = (INFINEON_BRAND_URL,) + PARTNER_BRAND_URL


def brand_for_image(brand_image_id: str) -> Brand:
    try:
        return BRANDS_BY_IMAGE[brand_image_id]
    except KeyError as exc:
        raise ValueError(
            f'Unknown brand image {brand_image_id!r}. '
            f'Choose from: {", ".join(BRAND_IMAGE_ID)}',
        ) from exc


def is_known_brand_image(brand_image_id: str) -> bool:
    return brand_image_id in BRANDS_BY_IMAGE

# ── Accelerators metadata links (fixed entries for metadata.json) ─────────

ACCELERATORS_DOWNLOAD_LINK = {
    'label': 'Download',
    'url': 'https://softwaretools.infineon.com/assets/com.ifx.tb.tool.deepcraftstudio',
    'heading': 'Access Project via DEEPCRAFT\u2122 Studio',
    'sub-heading': (
        'Download and install DEEPCRAFT\u2122 Studio to fully access this project '
        'and start developing your Edge AI product'
    ),
}

ACCELERATORS_GITHUB_LINK = {
    'label': 'GitHub',
    'heading': 'Project Repository',
    'sub-heading': 'Get more details about this project',
}

ACCELERATORS_GITHUB_URL = (
    'https://github.com/Infineon/deepcraft-studio-accelerators/tree/main/{project_name}'
)


def accelerator_links(project_name: str) -> list[dict]:
    """Build the two standard ``links`` entries for accelerators metadata.json."""
    return [
        dict(ACCELERATORS_DOWNLOAD_LINK),
        {
            **ACCELERATORS_GITHUB_LINK,
            'url': ACCELERATORS_GITHUB_URL.format(project_name=project_name),
        },
    ]


# ── Model zoo PSOC metadata links (fixed GitHub entry for metadata.json) ───

MODEL_ZOO_PSOC_GITHUB_LINK = {
    'label': 'GitHub',
    'heading': 'Try Today',
}

MODEL_ZOO_PSOC_GITHUB_URL = (
    'https://github.com/Infineon/deepcraft-model-zoo-for-psoc/tree/main/{project_name}'
)

MODEL_ZOO_PSOC_GITHUB_SUBHEADING_PREFIX = 'Deploy the pre-trained model to your '


def model_zoo_psoc_links(project_name: str, kits: list[str]) -> list[dict]:
    """Build the standard GitHub ``links`` entry for model-zoo-psoc metadata.json."""
    if not kits:
        raise ValueError('At least one kit must be selected before building project links')
    kit_name = kits[0]
    return [
        {
            **MODEL_ZOO_PSOC_GITHUB_LINK,
            'url': MODEL_ZOO_PSOC_GITHUB_URL.format(project_name=project_name),
            'sub-heading': f'{MODEL_ZOO_PSOC_GITHUB_SUBHEADING_PREFIX}{kit_name}',
        },
    ]
