# -*- coding: utf-8 -*-
# Generated by Django 1.11.29 on 2021-10-11 22:38
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('user', '0008_auto_20200209_1855'),
    ]

    operations = [
        migrations.AlterField(
            model_name='player',
            name='height_inches',
            field=models.IntegerField(blank=True, default=0),
        ),
    ]
