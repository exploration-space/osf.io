# -*- coding: utf-8 -*-
# Generated by Django 1.11.9 on 2018-02-21 19:11
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('osf', '0082_merge_20180213_1502'),
    ]

    operations = [
        migrations.AddField(
            model_name='noderequestaction',
            name='permissions',
            field=models.CharField(choices=[(b'admin', 'Admin'), (b'read', 'Read'), (b'write', 'Write')], default=b'read', max_length=5),
        ),
        migrations.AddField(
            model_name='noderequestaction',
            name='visible',
            field=models.BooleanField(default=True),
        ),
    ]
