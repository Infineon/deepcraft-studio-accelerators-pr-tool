"""Studio project templates published under ``_studio_templates``.

Names and titles are the templates on the accelerators ``main`` branch.
A project copied from one of them still carries that name, title, or link.
"""

STUDIO_TEMPLATE_LINK_MARKER = '_studio_templates'

# Folder name, then the title stored in that template's metadata.json.
STUDIO_TEMPLATES: tuple[tuple[str, str], ...] = (
    ('DataCollectionImageClassification', 'Data Collection Image Classification'),
    ('DataCollectionObjectDetection', 'Data Collection Object Detection'),
    ('EmptyClassificationProject', 'Empty Classification Project'),
    ('EmptyImageClassificationProject', 'Empty Image Classification Project'),
    ('EmptyObjectDetectionProject', 'Empty Object Detection Project'),
    ('EmptyProject', 'Empty Project'),
    ('EmptyRegressionProject', 'Empty Regression Project'),
    ('LiveDataCollection', 'Live Data Collection'),
    ('ModelEvaluation', 'Live Model Evaluation'),
    ('ModelEvaluationFromFile', 'Model Evaluation From File'),
    ('ModelEvaluationObjectDetection', 'Model Evaluation for Object Detection'),
    ('Yolo11n80ClassesModelEvaluation', 'Yolo11n 80 Classes Model Evaluation'),
    ('Yolo26n80ClassesModelEvaluation', 'Yolo26n 80 Classes Model Evaluation'),
    ('Yolov5n80ClassesModelEvaluation', 'Yolov5n 80 Classes Model Evaluation'),
    ('Yolov5nLegacy80ClassesModelEvaluation', 'Yolo5n Legacy 80Classes Model Evaluation'),
    ('Yolov8n80ClassesModelEvaluation', 'Yolov8n 80 Classes Model Evaluation'),
)

STUDIO_TEMPLATE_NAMES = frozenset(name for name, _title in STUDIO_TEMPLATES)
_STUDIO_TEMPLATE_TITLES = frozenset(title.casefold() for _name, title in STUDIO_TEMPLATES)


def is_studio_template_name(project_name: str) -> bool:
    """True when *project_name* is a Studio template folder name."""
    return project_name in STUDIO_TEMPLATE_NAMES


def is_studio_template_title(title: str) -> bool:
    """True when *title* equals a Studio template title."""
    return title.strip().casefold() in _STUDIO_TEMPLATE_TITLES


def is_studio_template_link(url: str) -> bool:
    """True when *url* still points inside ``_studio_templates``."""
    return STUDIO_TEMPLATE_LINK_MARKER in url.casefold()
