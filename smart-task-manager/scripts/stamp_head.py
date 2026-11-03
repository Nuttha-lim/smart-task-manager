from alembic.config import Config
from alembic import command
import os

cfg = Config(os.path.join(os.getcwd(),'alembic.ini'))
cfg.set_main_option('script_location', os.path.join(os.getcwd(),'alembic'))
command.stamp(cfg, 'head')
print('Stamped head')
