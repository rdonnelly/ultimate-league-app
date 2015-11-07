# -*- coding: utf-8 -*-

import os.path
import uuid

from django.db import models
from django.contrib.auth.models import User
from django.core.urlresolvers import reverse
from django.utils.html import strip_tags
from django.utils.translation import ugettext_lazy as _

from annoying.fields import AutoOneToOneField
from pybb.util import unescape

try:
    from hashlib import sha1
except ImportError:
    from sha import sha as sha1

try:
    from django.utils.timezone import now as tznow
except ImportError:
    import datetime
    tznow = datetime.datetime.now

from pybb import defaults


TZ_CHOICES = [(float(x[0]), x[1]) for x in (
(-12, '-12'), (-11, '-11'), (-10, '-10'), (-9.5, '-09.5'), (-9, '-09'),
(-8.5, '-08.5'), (-8, '-08 PST'), (-7, '-07 MST'), (-6, '-06 CST'),
(-5, '-05 EST'), (-4, '-04 AST'), (-3.5, '-03.5'), (-3, '-03 ADT'),
(-2, '-02'), (-1, '-01'), (0, '00 GMT'), (1, '+01 CET'), (2, '+02'),
(3, '+03'), (3.5, '+03.5'), (4, '+04'), (4.5, '+04.5'), (5, '+05'),
(5.5, '+05.5'), (6, '+06'), (6.5, '+06.5'), (7, '+07'), (8, '+08'),
(9, '+09'), (9.5, '+09.5'), (10, '+10'), (10.5, '+10.5'), (11, '+11'),
(11.5, '+11.5'), (12, '+12'), (13, '+13'), (14, '+14'),
)]


class Category(models.Model):
    name = models.CharField(_('Name'), max_length=80)
    position = models.IntegerField(_('Position'), blank=True, default=0)
    hidden = models.BooleanField(_('Hidden'), blank=False, null=False, default=False,
        help_text = _('If checked, this category will be visible only for staff')
    )

    class Meta(object):
        ordering = ['position']
        verbose_name = _('Category')
        verbose_name_plural = _('Categories')

    def __unicode__(self):
        return self.name

    def forum_count(self):
        return self.forums.all().count()

    def get_absolute_url(self):
        return reverse('pybb:category', kwargs={'pk': self.id})

    @property
    def topics(self):
        return Topic.objects.filter(forum__category=self).select_related()

    @property
    def posts(self):
        return Post.objects.filter(topic__forum__category=self).select_related()


class Forum(models.Model):
    category = models.ForeignKey(Category, related_name='forums', verbose_name=_('Category'))
    name = models.CharField(_('Name'), max_length=80)
    position = models.IntegerField(_('Position'), blank=True, default=0)
    description = models.TextField(_('Description'), blank=True)
    moderators = models.ManyToManyField(User, blank=True, verbose_name=_('Moderators'))
    updated = models.DateTimeField(_('Updated'), blank=True, null=True)
    post_count = models.IntegerField(_('Post count'), blank=True, default=0)
    topic_count = models.IntegerField(_('Topic count'), blank=True, default=0)
    hidden = models.BooleanField(_('Hidden'), blank=False, null=False, default=False)
    headline = models.TextField(_('Headline'), blank=True, null=True)

    class Meta(object):
        ordering = ['position']
        verbose_name = _('Forum')
        verbose_name_plural = _('Forums')

    def __unicode__(self):
        return self.name

    def update_counters(self):
        posts = Post.objects.filter(topic__forum_id=self.id)
        self.post_count = posts.count()
        self.topic_count = Topic.objects.filter(forum=self).count()
        try:
            last_post = posts.order_by('-created')[0]
            self.updated = last_post.updated or last_post.created
        except IndexError:
            pass

        self.save()

    def get_absolute_url(self):
        return reverse('pybb:forum', kwargs={'pk': self.id})

    @property
    def posts(self):
        return Post.objects.filter(topic__forum=self).select_related()

    def get_last_post(self):
        try:
            return self.posts.order_by('-created')[0]
        except IndexError:
            return None

    @property
    def last_post(self):
        return self.get_last_post()

    def get_parents(self):
        """
        Used in templates for breadcrumb building
        """
        return self.category,


class Topic(models.Model):
    POLL_TYPE_NONE = 0
    POLL_TYPE_SINGLE = 1
    POLL_TYPE_MULTIPLE = 2

    POLL_TYPE_CHOICES = (
        (POLL_TYPE_NONE, _('None')),
        (POLL_TYPE_SINGLE, _('Single answer')),
        (POLL_TYPE_MULTIPLE, _('Multiple answers')),
    )

    forum = models.ForeignKey(Forum, related_name='topics', verbose_name=_('Forum'))
    name = models.CharField(_('Subject'), max_length=255)
    created = models.DateTimeField(_('Created'), null=True)
    updated = models.DateTimeField(_('Updated'), null=True)
    user = models.ForeignKey(User, verbose_name=_('User'))
    views = models.IntegerField(_('Views count'), blank=True, default=0)
    sticky = models.BooleanField(_('Sticky'), blank=True, default=False)
    closed = models.BooleanField(_('Closed'), blank=True, default=False)
    post_count = models.IntegerField(_('Post count'), blank=True, default=0)
    on_moderation = models.BooleanField(_('On moderation'), default=False)
    poll_type = models.IntegerField(_('Poll type'), choices=POLL_TYPE_CHOICES, default=POLL_TYPE_NONE)
    poll_question = models.TextField(_('Poll question'), blank=True, null=True)

    class Meta(object):
        ordering = ['-created']
        verbose_name = _('Topic')
        verbose_name_plural = _('Topics')

    def __unicode__(self):
        return self.name

    @property
    def head(self):
        """
        Get first post and cache it for request
        """
        if not hasattr(self, "_head"):
            self._head = self.posts.all().order_by('created')
        if not len(self._head):
            return None
        return self._head[0]

    def get_last_post(self):
        return self.posts.order_by('-created').select_related('user')[0]

    @property
    def last_post(self):
        return self.get_last_post()

    def get_absolute_url(self):
        return reverse('pybb:topic', kwargs={'pk': self.id})

    def save(self, *args, **kwargs):
        if self.id is None:
            self.created = tznow()
        super(Topic, self).save(*args, **kwargs)

    def delete(self, using=None):
        super(Topic, self).delete(using)
        self.forum.update_counters()

    def update_counters(self):
        self.post_count = self.posts.count()
        last_post = Post.objects.filter(topic_id=self.id).order_by('-created')[0]
        self.updated = last_post.updated or last_post.created
        self.save()

    def get_parents(self):
        """
        Used in templates for breadcrumb building
        """
        return self.forum.category, self.forum

    def poll_votes(self):
        if self.poll_type != self.POLL_TYPE_NONE:
            return PollAnswerUser.objects.filter(poll_answer__topic=self).count()
        else:
            return None


class RenderableItem(models.Model):
    """
    Base class for models that has markup, body, body_text and body_html fields.
    """

    class Meta(object):
        abstract = True

    body = models.TextField(_('Message'))
    body_html = models.TextField(_('HTML version'))
    body_text = models.TextField(_('Text version'))

    def render(self):
        self.body_html = defaults.PYBB_MARKUP_ENGINES[defaults.PYBB_MARKUP](self.body)
        # Remove tags which was generated with the markup processor
        text = strip_tags(self.body_html)
        # Unescape entities which was generated with the markup processor
        self.body_text = unescape(text)


class Post(RenderableItem):
    topic = models.ForeignKey(Topic, related_name='posts', verbose_name=_('Topic'))
    user = models.ForeignKey(User, related_name='posts', verbose_name=_('User'))
    created = models.DateTimeField(_('Created'), blank=True, db_index=True)
    updated = models.DateTimeField(_('Updated'), blank=True, null=True)
    user_ip = models.GenericIPAddressField(_('User IP'), blank=True, null=True, default='0.0.0.0')
    on_moderation = models.BooleanField(_('On moderation'), default=False)

    class Meta(object):
        ordering = ['created']
        verbose_name = _('Post')
        verbose_name_plural = _('Posts')

    def summary(self):
        LIMIT = 50
        tail = len(self.body) > LIMIT and '...' or ''
        return self.body[:LIMIT] + tail

    __unicode__ = summary

    def save(self, *args, **kwargs):
        created_at = tznow()
        if self.created is None:
            self.created = created_at
        self.render()

        new = self.pk is None

        update_counters = kwargs.pop('update_counters', True)

        super(Post, self).save(*args, **kwargs)

        # If post is topic head and moderated, moderate topic too
        if self.topic.head == self and self.on_moderation == False and self.topic.on_moderation == True:
            self.topic.on_moderation = False
        if update_counters:
            self.topic.update_counters()
            self.topic.forum.update_counters()

    def get_absolute_url(self):
        return reverse('pybb:post', kwargs={'pk': self.id})

    def delete(self, *args, **kwargs):
        self_id = self.id
        head_post_id = self.topic.posts.order_by('created')[0].id

        if self_id == head_post_id:
            self.topic.delete()
        else:
            super(Post, self).delete(*args, **kwargs)
            self.topic.update_counters()
            self.topic.forum.update_counters()

    def get_parents(self):
        """
        Used in templates for breadcrumb building
        """
        return self.topic.forum.category, self.topic.forum, self.topic,


class PybbProfile(models.Model):
    """
    Abstract class for user profile, site profile should be inherted from this class
    """

    class Meta(object):
        abstract = True
        permissions = (
            ("block_users", "Can block any user"),
        )

    post_count = models.IntegerField(_('Post count'), blank=True, default=0)

    def save(self, *args, **kwargs):
        super(PybbProfile, self).save(*args, **kwargs)


class Profile(PybbProfile):
    """
    Profile class that can be used if you doesn't have
    your site profile.
    """
    user = AutoOneToOneField(User, related_name='pybb_profile', verbose_name=_('User'))

    class Meta(object):
        verbose_name = _('Profile')
        verbose_name_plural = _('Profiles')

    def get_absolute_url(self):
        return reverse('pybb:user', kwargs={'username': self.user.username})


class PollAnswer(models.Model):
    topic = models.ForeignKey(Topic, related_name='poll_answers', verbose_name=_('Topic'))
    text = models.CharField(max_length=255, verbose_name=_('Text'))

    class Meta:
        verbose_name = _('Poll answer')
        verbose_name_plural = _('Polls answers')

    def __unicode__(self):
        return self.text

    def votes(self):
        return self.users.count()

    def votes_percent(self):
        topic_votes = self.topic.poll_votes()
        if topic_votes > 0:
            return 1.0 * self.votes() / topic_votes * 100


class PollAnswerUser(models.Model):
    poll_answer = models.ForeignKey(PollAnswer, related_name='users', verbose_name=_('Poll answer'))
    user = models.ForeignKey(User, related_name='poll_answers', verbose_name=_('User'))
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('Poll answer user')
        verbose_name_plural = _('Polls answers users')
        unique_together = (('poll_answer', 'user', ), )

    def __unicode__(self):
        return u'%s - %s' % (self.poll_answer.topic, self.user)


from pybb import signals
signals.setup_signals()