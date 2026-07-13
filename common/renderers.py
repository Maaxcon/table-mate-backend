from rest_framework.renderers import BaseRenderer


class PNGRenderer(BaseRenderer):
    """Passes raw PNG bytes straight through DRF's response pipeline.

    Without this, a view that wants a binary image response has to bypass DRF
    (return a raw HttpResponse), which also makes drf-spectacular report the
    wrong content type in the generated schema — it derives media type from
    the view's renderer_classes, not from what the response actually sends.
    """

    media_type = "image/png"
    format = "png"
    charset = None
    render_style = "binary"

    def render(self, data: bytes, accepted_media_type: str | None = None, renderer_context: object = None) -> bytes:
        return data
