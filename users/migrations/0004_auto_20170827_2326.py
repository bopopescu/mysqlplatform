# -*- coding: utf-8 -*-
# Generated by Django 1.11.3 on 2017-08-27 15:26
from __future__ import unicode_literals

import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0003_messagerecord'),
    ]

    operations = [
        migrations.AlterField(
            model_name='messagerecord',
            name='send_time',
            field=models.DateTimeField(default=datetime.datetime.now, verbose_name='\u53d1\u9001\u65f6\u95f4'),
        ),
    ]
