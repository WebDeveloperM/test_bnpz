from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    EmployeeLoginView, EmployeeManualListView, EmployeeOfferAcceptView, SubmitView, CheckAnswerView,
    RecordingUploadView, RecordingDurationView,
    AdminLoginView, AdminMeView, AdminPermissionCatalogView,
    AdminRoleViewSet, AdminUserViewSet,
    AdminResultsListView, AdminResultDetailView, AdminResultsCsvView, AdminSettingsView,
    AdminOfferVideoView,
    AdminSeedDemoView, AdminClearDataView, AdminResultProtocolView,
    AdminRecordingsCleanupView, AdminRecordingDeleteView, AdminRecordingsBulkDeleteView,
    AdminRecordingsArchiveView,
    AdminActiveAttemptsView,
    AdminActivityLogView, AdminRecordingsListView, AdminSystemStatusView,
    TestAdminViewSet, QuestionAdminViewSet, EmployeeAdminViewSet, QuestionGroupAdminViewSet,
    QuestionImageView, OptionImageView, QuestionImportView,
    EmployeeSessionView, EmployeeLockAnswerView,
    EmployeeIdentifyView, EmployeeCheckinStatusView, AdminCheckinListView, AdminCheckinStartView,
    AdminEmployeeSyncView, AdminEmployeeSyncStatusView, AdminTsexListView,
    AdminSyncedEmployeeSearchView, AdminSyncedEmployeePhotoUploadView,
    AdminExpectedEmployeeListView, AdminExpectedEmployeeDeleteView,
    EmployeeLiveOfferView, EmployeeLiveSignalView, EmployeeLiveStatusView,
    AdminLiveOfferView, AdminLiveAnswerView, AdminLiveSignalView, AdminLiveStatusView,
    PublicResultProtocolView, PublicRecordingView, public_protocol_page,
)

router = DefaultRouter()
router.register("admin/tests", TestAdminViewSet, basename="admin-tests")
router.register("admin/questions", QuestionAdminViewSet, basename="admin-questions")
router.register("admin/groups", QuestionGroupAdminViewSet, basename="admin-groups")
router.register("admin/employees", EmployeeAdminViewSet, basename="admin-employees")
# Rollar va panel foydalanuvchilari — faqat superuser uchun (`IsSuperUser`).
router.register("admin/roles", AdminRoleViewSet, basename="admin-roles")
router.register("admin/users", AdminUserViewSet, basename="admin-users")

urlpatterns = [
    path("employee/login/", EmployeeLoginView.as_view()),
    path("employee/manual-list/", EmployeeManualListView.as_view()),
    path("employee/offer-accept/", EmployeeOfferAcceptView.as_view()),
    path("employee/submit/", SubmitView.as_view()),
    path("employee/check/", CheckAnswerView.as_view()),
    path("employee/session/", EmployeeSessionView.as_view()),
    path("employee/lock-answer/", EmployeeLockAnswerView.as_view()),
    path("employee/recording/", RecordingUploadView.as_view()),
    path("employee/recording/duration/", RecordingDurationView.as_view()),
    path("employee/identify/", EmployeeIdentifyView.as_view()),
    path("employee/checkin-status/", EmployeeCheckinStatusView.as_view()),
    # Tashqi dashboard uchun — LOGINSIZ. Tabel raqami bo'yicha natija,
    # protokol va (imzolangan, muddatli havolali) video. Batafsil izoh va
    # xavfsizlik chegarasi: core/views.py, `PublicResultProtocolView`.
    # DIQQAT: "protocol/view/" "protocol/" dan OLDIN turishi shart emas (yo'llar
    # aniq mos kelishi bo'yicha tanlanadi), lekin tartib o'qishga qulay bo'lsin.
    path("public/protocol/", PublicResultProtocolView.as_view()),
    path("public/protocol/view/", public_protocol_page),
    path("public/recording/", PublicRecordingView.as_view()),
    path("settings/", AdminSettingsView.as_view()),
    path("admin/settings/offer-video/", AdminOfferVideoView.as_view()),
    path("admin/login/", AdminLoginView.as_view()),
    path("admin/me/", AdminMeView.as_view()),
    path("admin/permissions/", AdminPermissionCatalogView.as_view()),
    path("admin/active-attempts/", AdminActiveAttemptsView.as_view()),
    path("admin/checkins/", AdminCheckinListView.as_view()),
    path("admin/checkins/<int:pk>/start/", AdminCheckinStartView.as_view()),
    path("admin/employee-service/sync/", AdminEmployeeSyncView.as_view()),
    path("admin/employee-service/sync-status/", AdminEmployeeSyncStatusView.as_view()),
    path("admin/tsex-list/", AdminTsexListView.as_view()),
    path("admin/synced-employees/search/", AdminSyncedEmployeeSearchView.as_view()),
    path("admin/synced-employees/<int:pk>/photo/", AdminSyncedEmployeePhotoUploadView.as_view()),
    path("admin/expected-employees/", AdminExpectedEmployeeListView.as_view()),
    path("admin/expected-employees/<int:pk>/", AdminExpectedEmployeeDeleteView.as_view()),
    path("admin/results/", AdminResultsListView.as_view()),
    path("admin/results/csv/", AdminResultsCsvView.as_view()),
    path("admin/results/<int:pk>/", AdminResultDetailView.as_view()),
    path("admin/results/<int:pk>/protocol/", AdminResultProtocolView.as_view()),
    path("admin/recordings/cleanup/", AdminRecordingsCleanupView.as_view()),
    # Tizim bo'limlari — endi ular ham rolga beriladi (avval faqat superuserda edi)
    path("admin/activity/", AdminActivityLogView.as_view()),
    path("admin/recordings/", AdminRecordingsListView.as_view()),
    # Filtrlangan yozuvlarni bitta .zip da yuklab olish. "bulk-delete" kabi,
    # bu ham `<int:pk>` dan OLDIN turishi shart — aks holda "archive" bo'lagi
    # pk sifatida talqin qilinmoqchi bo'lardi.
    path("admin/recordings/archive/", AdminRecordingsArchiveView.as_view()),
    # O'chirish — faqat superuser (`IsSuperUser`): bittalab yoki tanlanganlarni.
    # Diqqat: "bulk-delete" `<int:pk>` dan OLDIN turishi shart, aks holda
    # "bulk-delete" bo'lagi pk sifatida talqin qilinmoqchi bo'lardi.
    path("admin/recordings/bulk-delete/", AdminRecordingsBulkDeleteView.as_view()),
    path("admin/recordings/<int:pk>/", AdminRecordingDeleteView.as_view()),
    path("admin/system-status/", AdminSystemStatusView.as_view()),
    path("admin/questions/<int:pk>/image/", QuestionImageView.as_view()),
    path("admin/options/<int:pk>/image/", OptionImageView.as_view()),
    path("admin/questions/import/", QuestionImportView.as_view()),
    path("admin/seed-demo/", AdminSeedDemoView.as_view()),
    path("admin/clear-data/", AdminClearDataView.as_view()),
    # WebRTC signaling
    path("employee/live/offer/", EmployeeLiveOfferView.as_view()),
    path("employee/live/signal/", EmployeeLiveSignalView.as_view()),
    path("employee/live/status/", EmployeeLiveStatusView.as_view()),
    path("admin/live/<int:attempt_id>/offer/", AdminLiveOfferView.as_view()),
    path("admin/live/<int:attempt_id>/answer/", AdminLiveAnswerView.as_view()),
    path("admin/live/<int:attempt_id>/signal/", AdminLiveSignalView.as_view()),
    # Jonli ko'rish oynasi ulangandan keyin shu yerdan "test tugadimi?" deb
    # so'rab turadi — "offer" endpointi buning uchun yaramaydi (yon ta'siri bor,
    # qarang: AdminLiveStatusView izohi).
    path("admin/live/<int:attempt_id>/status/", AdminLiveStatusView.as_view()),
    path("", include(router.urls)),
]
