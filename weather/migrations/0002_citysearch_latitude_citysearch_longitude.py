# Generated by Django 4.2.13 on 2024-07-19 12:47

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('weather', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='citysearch',
            name='latitude',
            field=models.FloatField(default=0.0),
        ),
        migrations.AddField(
            model_name='citysearch',
            name='longitude',
            field=models.FloatField(default=0.0),
        ),
    ]
