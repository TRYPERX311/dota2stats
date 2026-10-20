# Диаграмма видимости пиров
```mermaid
stateDiagram-v2
    [*] --> Гость

    state "Гость (любой профиль)" as Guest {
        note right of Guest
            Пиры скрыты
        end note
    }

    state "Авторизован" as Auth {
        [*] --> СвойПрофиль
        state "Свой профиль" as СвойПрофиль
        state "Чужой профиль" as ЧужойПрофиль

        note right of СвойПрофиль
            Пиры видны
        end note
        note right of ЧужойПрофиль
            Пиры скрыты
        end note

        СвойПрофиль --> ЧужойПрофиль: клик по другому игроку
        ЧужойПрофиль --> СвойПрофиль: клик по себе / по лого
    }

    Guest --> Auth: логин
    Auth --> Guest: логаут
   ```
