from django import forms
from django.shortcuts import get_object_or_404, redirect
from django.template.defaultfilters import linebreaks_filter
from django.utils.decorators import method_decorator
from django.views.generic import FormView, ListView

from activities.models import Hashtag, Post, PostInteraction, TimelineEvent
from core.models import Config
from users.decorators import identity_required


@method_decorator(identity_required, name="dispatch")
class Home(FormView):

    template_name = "activities/home.html"

    class form_class(forms.Form):
        text = forms.CharField(
            widget=forms.Textarea(
                attrs={
                    "placeholder": "What's on your mind?",
                },
            )
        )
        content_warning = forms.CharField(
            required=False,
            label=Config.lazy_system_value("content_warning_text"),
            widget=forms.TextInput(
                attrs={
                    "class": "hidden",
                    "placeholder": Config.lazy_system_value("content_warning_text"),
                },
            ),
        )

    def get_context_data(self):
        context = super().get_context_data()
        context["events"] = list(
            TimelineEvent.objects.filter(
                identity=self.request.identity,
                type__in=[TimelineEvent.Types.post, TimelineEvent.Types.boost],
            )
            .select_related("subject_post", "subject_post__author")
            .prefetch_related("subject_post__attachments")
            .order_by("-created")[:50]
        )
        context["interactions"] = PostInteraction.get_event_interactions(
            context["events"], self.request.identity
        )
        context["current_page"] = "home"
        context["allows_refresh"] = True
        return context

    def form_valid(self, form):
        Post.create_local(
            author=self.request.identity,
            content=linebreaks_filter(form.cleaned_data["text"]),
            summary=form.cleaned_data.get("content_warning"),
            visibility=self.request.identity.config_identity.default_post_visibility,
        )
        return redirect(".")


class Tag(ListView):

    template_name = "activities/tag.html"
    extra_context = {
        "current_page": "tag",
        "allows_refresh": True,
    }
    paginate_by = 50

    def get(self, request, hashtag, *args, **kwargs):
        tag = hashtag.lower().lstrip("#")
        if hashtag != tag:
            # SEO sanitize
            return redirect(f"/tags/{tag}/", permanent=True)
        self.hashtag = get_object_or_404(Hashtag.objects.public(), hashtag=tag)
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        return (
            Post.objects.public()
            .tagged_with(self.hashtag)
            .select_related("author")
            .prefetch_related("attachments")
            .order_by("-created")[:50]
        )

    def get_context_data(self):
        context = super().get_context_data()
        context["hashtag"] = self.hashtag
        context["interactions"] = PostInteraction.get_post_interactions(
            context["page_obj"], self.request.identity
        )
        return context


class Local(ListView):

    template_name = "activities/local.html"
    extra_context = {
        "current_page": "local",
        "allows_refresh": True,
    }
    paginate_by = 50

    def get_queryset(self):
        return (
            Post.objects.local_public()
            .select_related("author")
            .prefetch_related("attachments")
            .order_by("-created")[:50]
        )

    def get_context_data(self):
        context = super().get_context_data()
        context["interactions"] = PostInteraction.get_post_interactions(
            context["page_obj"], self.request.identity
        )
        return context


@method_decorator(identity_required, name="dispatch")
class Federated(ListView):

    template_name = "activities/federated.html"
    extra_context = {
        "current_page": "federated",
        "allows_refresh": True,
    }
    paginate_by = 50

    def get_queryset(self):
        return (
            Post.objects.filter(
                visibility=Post.Visibilities.public, in_reply_to__isnull=True
            )
            .select_related("author")
            .prefetch_related("attachments")
            .order_by("-created")[:50]
        )

    def get_context_data(self):
        context = super().get_context_data()
        context["interactions"] = PostInteraction.get_post_interactions(
            context["page_obj"], self.request.identity
        )
        return context


@method_decorator(identity_required, name="dispatch")
class Notifications(ListView):

    template_name = "activities/notifications.html"
    extra_context = {
        "current_page": "notifications",
        "allows_refresh": True,
    }
    paginate_by = 50

    def get_queryset(self):
        return (
            TimelineEvent.objects.filter(
                identity=self.request.identity,
                type__in=[
                    TimelineEvent.Types.mentioned,
                    TimelineEvent.Types.boosted,
                    TimelineEvent.Types.liked,
                    TimelineEvent.Types.followed,
                ],
            )
            .order_by("-created")[:50]
            .select_related("subject_post", "subject_post__author", "subject_identity")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Collapse similar notifications into one
        events = []
        for event in context["page_obj"]:
            if (
                events
                and event.type
                in [
                    TimelineEvent.Types.liked,
                    TimelineEvent.Types.boosted,
                    TimelineEvent.Types.mentioned,
                ]
                and event.subject_post_id == events[-1].subject_post_id
            ):
                events[-1].collapsed = True
            events.append(event)
        context["events"] = events
        return context
