from app.db.database import Database
from app.db.repositories.mailing_lists import MailingListRepository
from app.db.repositories.notifications import NotificationRepository
from app.db.repositories.snapshots import SnapshotStore
from app.db.repositories.triggers import TriggerRepository
from app.services.alerts import AlertService
from app.services.email import EmailService
from app.services.ipos import IpoService


class Container:
    def __init__(self, settings):
        self.settings = settings
        self.database = Database(settings)
        self.snapshots = SnapshotStore(self.database)
        self.mailing_lists = MailingListRepository(self.database)
        self.notifications = NotificationRepository(self.database)
        self.triggers = TriggerRepository(self.database, self.mailing_lists)
        self.email = EmailService(settings)
        self.alerts = AlertService(
            self.database,
            self.triggers,
            self.mailing_lists,
            self.notifications,
            self.email,
        )
        self.ipos = IpoService(self.snapshots, self.alerts, settings)

    def start(self):
        self.database.open()
        try:
            self.database.check_ready()
        except Exception:
            self.database.close()
            raise

    def close(self):
        self.database.close()
