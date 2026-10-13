import { html, css } from "lit";
import { customElement, property } from "lit/decorators.js";
import type { HomeAssistant, RoomConfig } from "../../types";
import { localize } from "../../utils/localize";
import { tempUnit } from "../../utils/temperature";
import { RsSettingsBase } from "./rs-settings-base";

@customElement("rs-settings-tariff")
export class RsSettingsTariff extends RsSettingsBase {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ attribute: false }) public rooms: Record<string, RoomConfig> = {};
  @property({ type: Boolean }) public acTariffEnabled = false;
  @property({ type: String }) public acOffPeakStart = "00:00";
  @property({ type: String }) public acOffPeakEnd = "05:00";
  @property({ type: Boolean }) public acMorningBoostEnabled = false;
  @property({ type: Number }) public acMorningBoostMinutes = 30;
  @property({ type: Number }) public acMorningBoostStopMargin = 0.2;
  @property({ attribute: false }) public acMorningBoostRooms: string[] = [];
  private _t(key: string) {
    return localize(`tariff.${key}` as Parameters<typeof localize>[0], this.hass.language);
  }
  render() {
    const eligible = Object.entries(this.rooms).filter(
      ([, room]) =>
        !room.is_outdoor &&
        room.temperature_sensor &&
        (room.devices?.some((d) => d.type === "ac") || room.acs?.length) &&
        room.climate_mode !== "cool_only",
    );
    return html`
      <div class="settings-section first">
        <label class="toggle-row"
          ><span class="toggle-text"
            ><b>${this._t("lockout")}</b
            ><span class="toggle-hint">${this._t("lockout_hint")}</span></span
          ><ha-switch
            .checked=${this.acTariffEnabled}
            @change=${(e: Event) => this._fire("acTariffEnabled", (e.target as HTMLInputElement).checked)}
          ></ha-switch
        ></label>
      </div>
      <div class="threshold-grid">
        <label
          >${this._t("start")}<input
            type="time"
            .value=${this.acOffPeakStart}
            @change=${(e: Event) => {
              const v = (e.target as HTMLInputElement).value;
              if (v) this._fire("acOffPeakStart", v);
            }} /></label
        ><label
          >${this._t("end")}<input
            type="time"
            .value=${this.acOffPeakEnd}
            @change=${(e: Event) => {
              const v = (e.target as HTMLInputElement).value;
              if (v) this._fire("acOffPeakEnd", v);
            }}
        /></label>
      </div>
      <p class="hint">${this._t("utc_hint")}</p>
      <div class="settings-section">
        <label class="toggle-row"
          ><span class="toggle-text"
            ><b>${this._t("boost")}</b
            ><span class="toggle-hint">${this._t("boost_hint")}</span></span
          ><ha-switch
            .checked=${this.acMorningBoostEnabled}
            .disabled=${!this.acTariffEnabled}
            @change=${(e: Event) => this._fire("acMorningBoostEnabled", (e.target as HTMLInputElement).checked)}
          ></ha-switch
        ></label>
      </div>
      <div class="threshold-grid">
        <label
          >${this._t("lead")}<input
            type="number"
            min="5"
            max="120"
            step="5"
            .value=${String(this.acMorningBoostMinutes)}
            @change=${(e: Event) => {
              const v = Number((e.target as HTMLInputElement).value);
              if (v >= 5 && v <= 120) this._fire("acMorningBoostMinutes", v);
            }} /></label
        ><label
          >${this._t("stop_margin")} (${tempUnit(this.hass)})<input
            type="number"
            min="0"
            max=${this.hass.config.unit_system.temperature === "°F" ? 1.8 : 1}
            step="0.1"
            .value=${String(this.hass.config.unit_system.temperature === "°F" ? this.acMorningBoostStopMargin * 1.8 : this.acMorningBoostStopMargin)}
            @change=${(e: Event) => {
              const v = Number((e.target as HTMLInputElement).value);
              const offset = this.hass.config.unit_system.temperature === "°F" ? v / 1.8 : v;
              if (offset >= 0 && offset <= 1) this._fire("acMorningBoostStopMargin", offset);
            }}
        /></label>
      </div>
      <p class="hint">${this._t("stop_margin_hint")}</p>
      <p class="hint">${this._t("hold_hint")}</p>
      <b>${this._t("rooms")}</b>
      <div class="checks">
        ${eligible.map(([id, room]) => html`<label><input type="checkbox" .checked=${this.acMorningBoostRooms.includes(id)} @change=${(e: Event) => this._fire("acMorningBoostRooms", (e.target as HTMLInputElement).checked ? [...this.acMorningBoostRooms, id] : this.acMorningBoostRooms.filter((a) => a !== id))} />${room.display_name || this.hass.areas?.[id]?.name || id}</label>`)}
      </div>
      ${!eligible.length ? html`<p class="hint">${this._t("no_rooms")}</p>` : ""}
    `;
  }
  static styles = [
    RsSettingsBase.settingsBaseStyles,
    css`
      label {
        display: flex;
        flex-direction: column;
        gap: 8px;
        font-size: 14px;
      }
      label.toggle-row {
        flex-direction: row;
      }
      input {
        padding: 10px;
        min-width: 0;
        border: 1px solid var(--divider-color);
        border-radius: 8px;
        background: var(--card-background-color);
        color: var(--primary-text-color);
        font: inherit;
      }
      .hint {
        color: var(--secondary-text-color);
        font-size: 13px;
        line-height: 1.5;
      }
      .checks {
        display: flex;
        flex-wrap: wrap;
        gap: 16px;
        margin-top: 16px;
      }
      .checks label {
        flex-direction: row;
        align-items: center;
      }
      input[type="checkbox"] {
        width: 20px;
        height: 20px;
      }
    `,
  ];
}
