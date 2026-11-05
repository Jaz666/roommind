import { LitElement, html, css, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { HomeAssistant, RoomConfig, ScheduleChoice } from "../types";
import { formatTemp, tempUnit } from "../utils/temperature";
import { localize } from "../utils/localize";

@customElement("rs-schedule-link")
export class RsScheduleLink extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ attribute: false }) public config: RoomConfig | null = null;
  @property({ attribute: false }) public choices: ScheduleChoice[] = [];
  @property({ type: Boolean }) public editing = false;
  @state() private _busy = false;
  @state() private _error = "";
  private _t(key: string) {
    return localize(`weekly.${key}` as Parameters<typeof localize>[0], this.hass.language);
  }
  private async _assign(event: Event) {
    const input = event.target as HTMLSelectElement;
    const previous = this.config?.roommind_schedule_id || "";
    this._busy = true;
    this._error = "";
    try {
      await this.hass.callWS({
        type: "roommind/rooms/save",
        area_id: this.config!.area_id,
        roommind_schedule_id: input.value,
      });
      this.dispatchEvent(new CustomEvent("room-updated", { bubbles: true, composed: true }));
    } catch (err) {
      input.value = previous;
      this._error =
        typeof err === "object" && err && "message" in err ? String(err.message) : String(err);
    } finally {
      this._busy = false;
    }
  }
  render() {
    if (!this.hass || !this.config) return nothing;
    const schedule = this.config.roommind_schedule;
    const targets = schedule?.targets;
    const next = schedule?.next_change;
    const showCool =
      this.config.climate_mode !== "heat_only" &&
      (this.config.acs?.length || this.config.devices?.some((d) => d.type === "ac"));
    const format = (t: number) => `${formatTemp(t, this.hass)}${tempUnit(this.hass)}`;
    const when = next
      ? new Intl.DateTimeFormat(this.hass.language, {
          weekday: "short",
          hour: "2-digit",
          minute: "2-digit",
          timeZone: this.hass.config.time_zone,
        }).format(new Date(next * 1000))
      : "";
    return html`
      ${
        this.editing
          ? html`<label
                >${this._t("room_schedule")}<select
                  .value=${this.config.roommind_schedule_id || ""}
                  ?disabled=${this._busy}
                  @change=${this._assign}
                >
                  <option value="" ?selected=${!this.config.roommind_schedule_id}>
                    ${this._t("ha_schedule")}
                  </option>
                  ${this.choices.map((s) => html`<option value=${s.id} ?selected=${this.config?.roommind_schedule_id === s.id}>${s.name}</option>`)}
                </select></label
              >
              <p>${this._t("link_hint")}</p>`
          : nothing
      }
      ${
        schedule
          ? html`<p><strong>${schedule.name}</strong></p>
              ${targets ? html`<p>${this.config.climate_mode !== "cool_only" ? `${this._t("heat_below")} ${format(targets.heat_temperature)}` : ""}${this.config.climate_mode === "auto" && showCool ? " · " : ""}${showCool ? `${this._t("cool_above")} ${format(targets.cool_temperature)}` : ""}</p>` : nothing}
              <p>${next ? `${this._t("next_change")} ${when}` : this._t("constant_schedule")}</p>
              <p class="hint">${this._t("scheduled_hint")}</p> `
          : nothing
      }
      ${this.config.roommind_schedule_missing ? html`<p role="alert">${this._t("missing")}</p>` : nothing}
      <a
        href="/roommind/schedules"
        @click=${(e: Event) => {
          e.preventDefault();
          this.dispatchEvent(new CustomEvent("open-schedules", { bubbles: true, composed: true }));
        }}
        >${this._t("manage")}</a
      >
      ${this._error ? html`<p role="alert">${this._error}</p>` : nothing}
    `;
  }
  static styles = css`
    :host {
      display: block;
      margin-bottom: 16px;
    }
    label {
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    select {
      padding: 10px;
      border-radius: 8px;
      border: 1px solid var(--divider-color);
      background: var(--card-background-color);
      color: var(--primary-text-color);
      font: inherit;
    }
    p {
      margin: 8px 0;
      line-height: 1.5;
    }
    .hint {
      color: var(--secondary-text-color);
      font-size: 12px;
    }
    a {
      color: var(--primary-color);
    }
    [role="alert"] {
      color: var(--error-color);
    }
  `;
}
