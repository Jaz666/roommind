# AC heating tariff and Morning Boost

RoomMind can block AC heating during peak electricity hours while allowing cooling and radiator heating. During the configured off-peak window, AC heating remains available, including for Heat Only rooms.

Morning Boost can prepare selected AC rooms for their next scheduled heating target near the end of the off-peak window. It retains its configured lead time, stop margin, and post-cutoff cooling handover. Room device setpoint modes continue to apply during the boost.

Configure this under **Settings → Mods → Electricity tariff**. The default window is 00:00–05:00 GMT / UTC and does not shift for daylight saving time. Home Assistant room schedules continue to use local time. Select the rooms for Morning Boost in the same section.

During peak hours, RoomMind prevents AC heating, including heating overrides and AC idle setback. Cooling remains available and still blocks radiator heating in the room being cooled. AC-only rooms cannot heat during peak hours. The lockout applies to RoomMind commands; it does not block commands from the Toshiba app or other automations.

Room cards show **AC heat locked (peak)** when the lockout applies. This reports RoomMind's command policy, not proof that the compressor is physically running.
