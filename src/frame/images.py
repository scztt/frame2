import os
from typing import Any, Dict
import tempfile


class ImageRef:
    def __init__(self, id: str, path: str):
        self.id = id
        self.path = path
        self.url = "images/" + id

    @property
    def extension(self):
        return os.path.splitext(self.path)[1]

    # @property
    # def url(self):
    #     return self.url

    # @property
    # def path(self):
    #     return self.path

    @property
    def stream(self):
        return (open(self.path, "rb"), self.extension)


class ImageRepo:
    def __init__(self, settings: Dict[str, Any]):
        self.settings = settings
        self.dir = tempfile.TemporaryDirectory()
        self.images = {}

    def make_image_ref(self, unique_id: str) -> ImageRef:
        path = os.path.join(self.dir.name, unique_id)
        ref = ImageRef(unique_id, path)
        self.images[unique_id] = ref
        return ref

    def get_image_ref(self, id: str) -> ImageRef:
        image = self.images.get(id)
        if image is None:
            image = self.make_image_ref(id)

        return image

    def get_image_stream(self, id: str) -> bytes:
        return self.get_image_ref(id).stream


image_repo = ImageRepo({})
