import os
from typing import Any, Dict
import tempfile
import uuid


class ImageRef:
    id: str
    uid: str
    mod_time: float

    def __init__(self, id: str, path: str):
        self.id = id
        self.path = path
        self.url = "images/" + id
        self.uid = uuid.uuid4().hex

    @property
    def extension(self):
        return os.path.splitext(self.path)[1]

    def __eq__(self, other) -> bool:
        return type(self) is type(other) and self.id == other.id and self.uid == other.uid


class ImageRepo:
    def __init__(self, settings: Dict[str, Any]):
        self.settings = settings
        self.dir = tempfile.TemporaryDirectory()
        self.images: Dict[str, ImageRef] = {}

    def make_image_ref(self, unique_id: str) -> ImageRef:
        path = os.path.join(self.dir.name, unique_id)
        ref = ImageRef(unique_id, path)
        self.images[unique_id] = ref
        return ref

    def get_image_ref(self, id: str) -> ImageRef:
        image = self.images.get(id)
        if image is None:
            return self.make_image_ref(id)
        else:
            return image

    def get_image_path(self, id: str) -> str:
        return self.get_image_ref(id).path


image_repo = ImageRepo({})
