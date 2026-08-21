# Generated manually
from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('tenants', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='PublicConfiguration',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('base_domain', models.CharField(default='localhost', max_length=255)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
        ),
    ]
