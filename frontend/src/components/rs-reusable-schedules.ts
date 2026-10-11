import { LitElement, html, css, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { HomeAssistant, RoomConfig, ReusableSchedule, WeeklyBlock } from "../types";
import { toDisplay, toCelsius, tempUnit, tempStep } from "../utils/temperature";
import { localize } from "../utils/localize";

const DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"];
const minutes = (time: string) => Number(time.slice(0, 2)) * 60 + Number(time.slice(3, 5));
const time = (value: number) =>
  `${String(Math.floor(value / 60)).padStart(2, "0")}:${String(value % 60).padStart(2, "0")}:00`;
const clone = <T>(value: T): T => structuredClone(value);

@customElement("rs-reusable-schedules")
export class RsReusableSchedules extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ attribute: false }) public rooms: Record<string, RoomConfig> = {};
  @state() private _schedules: Record<string, ReusableSchedule> = {};
  @state() private _draft: ReusableSchedule | null = null;
  @state() private _day = "monday";
  @state() private _copyDays: string[] = DAYS.slice(1);
  @state() private _error = "";
  @state() private _busy = false;
  @state() private _loaded = false;
  @state() private _dirty = false;
  @state() private _importEntity = "";
  @state() private _importHeat = 19;
  @state() private _importCool = 19.5;
  private _invalidInputs = new Set<string>();
  private _dragCleanup?: () => void;
  private _beforeUnload = (event: BeforeUnloadEvent) => {
    if (this._dirty) {
      event.preventDefault();
      event.returnValue = "";
    }
  };
  // Parent uses this to protect unsaved work when changing tabs.
  public canLeave(): boolean {
    return !this._dirty || window.confirm(this._t("discard"));
  }
  private _t(key: string): string {
    return localize(`weekly.${key}` as Parameters<typeof localize>[0], this.hass.language);
  }
  connectedCallback() {
    super.connectedCallback();
    window.addEventListener("beforeunload", this._beforeUnload);
    if (this.hass) void this._load();
  }
  disconnectedCallback() {
    super.disconnectedCallback();
    this._dragCleanup?.();
    window.removeEventListener("beforeunload", this._beforeUnload);
  }
  protected updated(changed: Map<string, unknown>) {
    if (changed.has("hass") && this.hass && !this._loaded && !this._busy) void this._load();
  }
  private async _load() {
    this._busy = true;
    try {
      const result = await this.hass.callWS<{ schedules: Record<string, ReusableSchedule> }>({
        type: "roommind/schedules/list",
      });
      this._schedules = result.schedules;
      this._loaded = true;
    } catch (err) {
      this._error = this._message(err);
    } finally {
      this._busy = false;
    }
  }
  private _message(err: unknown): string {
    return typeof err === "object" && err && "message" in err ? String(err.message) : String(err);
  }
  private _weekday(day: string): string {
    return new Intl.DateTimeFormat(this.hass.language, { weekday: "long", timeZone: "UTC" }).format(
      new Date(Date.UTC(2024, 0, 1 + DAYS.indexOf(day))),
    );
  }
  private _roomName(id: string): string {
    return this.rooms[id]?.display_name || this.hass.areas?.[id]?.name || id;
  }
  private _begin(schedule?: ReusableSchedule, preset = "") {
    if (!this.canLeave()) return;
    this._error = "";
    this._invalidInputs.clear();
    this._dirty = false;
    this._day = "monday";
    this._copyDays = DAYS.slice(1);
    if (schedule) {
      this._draft = clone(schedule);
      return;
    }
    const heat = preset === "Living Room" ? 21 : 20;
    const night = preset === "Bedrooms" ? 19 : heat;
    const blocks: WeeklyBlock[] = [
      {
        from: "00:00:00",
        to: "07:00:00",
        data: { heat_temperature: night, cool_temperature: night + 0.5 },
      },
      {
        from: "07:00:00",
        to: "22:00:00",
        data: { heat_temperature: heat, cool_temperature: heat + 0.5 },
      },
      {
        from: "22:00:00",
        to: "24:00:00",
        data: { heat_temperature: night, cool_temperature: night + 0.5 },
      },
    ];
    this._draft = {
      id: "",
      revision: 0,
      name: preset,
      days: Object.fromEntries(DAYS.map((d) => [d, clone(blocks)])),
      area_ids: [],
    };
    this._dirty = true;
  }
  private _change() {
    this._draft = clone(this._draft!);
    this._dirty = true;
    this._error = this._invalidInputs.size ? this._t("invalid_inputs") : "";
  }
  private _clearDayErrors() {
    this._invalidInputs = new Set(
      [...this._invalidInputs].filter((key) => !key.startsWith(`${this._day}:`)),
    );
  }
  private _boundary(index: number, value: number) {
    const blocks = this._draft!.days[this._day];
    if (
      !Number.isFinite(value) ||
      value <= minutes(blocks[index].from) ||
      value >= minutes(blocks[index + 1].to)
    ) {
      this._invalidInputs.add(`${this._day}:boundary:${index}`);
      this._error = this._t("invalid_time");
      return;
    }
    this._invalidInputs.delete(`${this._day}:boundary:${index}`);
    blocks[index].to = blocks[index + 1].from = time(value);
    this._change();
  }
  private _drag(event: PointerEvent, index: number) {
    if (this._busy) return;
    event.preventDefault();
    const timeline = (event.currentTarget as HTMLElement).parentElement!.getBoundingClientRect();
    const move = (e: PointerEvent) => {
      const blocks = this._draft!.days[this._day];
      const value = Math.round((((e.clientX - timeline.left) / timeline.width) * 1440) / 15) * 15;
      this._boundary(
        index,
        Math.max(
          minutes(blocks[index].from) + 15,
          Math.min(minutes(blocks[index + 1].to) - 15, value),
        ),
      );
    };
    this._dragCleanup?.();
    this._dragCleanup = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", end);
      window.removeEventListener("pointercancel", end);
      this._dragCleanup = undefined;
    };
    const end = () => this._dragCleanup?.();
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", end, { once: true });
    window.addEventListener("pointercancel", end, { once: true });
  }
  private _split(index: number) {
    const blocks = this._draft!.days[this._day];
    const block = blocks[index];
    const start = minutes(block.from),
      end = minutes(block.to);
    if (end - start < 2 || blocks.length >= 48) return;
    const middle = time(Math.floor((start + end) / 2));
    this._clearDayErrors();
    blocks.splice(index, 1, { ...clone(block), to: middle }, { ...clone(block), from: middle });
    this._change();
  }
  private _remove(index: number) {
    const blocks = this._draft!.days[this._day];
    if (blocks.length === 1) return;
    if (index === 0) blocks[1].from = blocks[0].from;
    else blocks[index - 1].to = blocks[index].to;
    this._clearDayErrors();
    blocks.splice(index, 1);
    this._change();
  }
  private _temp(index: number, field: "heat_temperature" | "cool_temperature", event: Event) {
    const input = event.target as HTMLInputElement;
    const key = `${this._day}:temp:${index}:${field}`;
    if (input.value === "") {
      this._invalidInputs.add(key);
      this._error = this._t("invalid_temp");
      return;
    }
    const value = toCelsius(Number(input.value), this.hass);
    if (!Number.isFinite(value) || value < 5 || value > 35) {
      this._invalidInputs.add(key);
      this._error = this._t("invalid_temp");
      return;
    }
    this._invalidInputs.delete(key);
    const data = this._draft!.days[this._day][index].data;
    data[field] = value;
    // Heating-only schedules still store a valid band for later AC assignments.
    if (!this._showCool() && field === "heat_temperature")
      data.cool_temperature = Math.max(value, data.cool_temperature);
    this._change();
  }
  private _showCool(): boolean {
    const ids = this._draft?.area_ids ?? [];
    return (
      !ids.length ||
      ids.some(
        (id) =>
          this.rooms[id]?.climate_mode !== "heat_only" &&
          (this.rooms[id]?.acs?.length || this.rooms[id]?.devices?.some((d) => d.type === "ac")),
      )
    );
  }
  private _copyDay() {
    if (this._invalidInputs.size) {
      this._error = this._t("invalid_inputs");
      return;
    }
    for (const day of this._copyDays)
      if (day !== this._day) this._draft!.days[day] = clone(this._draft!.days[this._day]);
    this._change();
  }
  private _validate(): string {
    if (this._invalidInputs.size) return this._t("invalid_inputs");
    if (!this._draft!.name.trim()) return this._t("name_required");
    for (const day of DAYS)
      for (const block of this._draft!.days[day]) {
        if (block.data.heat_temperature > block.data.cool_temperature)
          return this._t("invalid_band");
      }
    return "";
  }
  private async _save() {
    this._error = this._validate();
    if (this._error) return;
    this._busy = true;
    try {
      const draft = this._draft!;
      await this.hass.callWS({
        type: "roommind/schedules/save",
        schedule_id: draft.id,
        revision: draft.revision,
        name: draft.name,
        days: draft.days,
        area_ids: draft.area_ids,
      });
      this._dirty = false;
      this._draft = null;
      await this._load();
      this.dispatchEvent(new CustomEvent("schedules-updated", { bubbles: true, composed: true }));
    } catch (err) {
      this._error = this._message(err);
    } finally {
      this._busy = false;
    }
  }
  private async _delete(schedule: ReusableSchedule) {
    if (!window.confirm(this._t("delete_confirm"))) return;
    this._busy = true;
    try {
      await this.hass.callWS({
        type: "roommind/schedules/delete",
        schedule_id: schedule.id,
        revision: schedule.revision,
      });
      this._draft = null;
      this._dirty = false;
      await this._load();
    } catch (err) {
      this._error = this._message(err);
    } finally {
      this._busy = false;
    }
  }
  render() {
    if (!this.hass) return nothing;
    return html`<section>
      <h2>${this._t("title")}</h2>
      <p>${this._t("intro")}</p>
      ${this._error ? html`<p class="error" role="alert">${this._error}</p>` : nothing}
      ${
        !this._loaded
          ? html`<p>${this._busy ? this._t("loading") : this._t("load_failed")}</p>
              <button ?disabled=${this._busy} @click=${() => this._load()}>
                ${this._t("reload")}
              </button>`
          : this._draft
            ? this._editor()
            : this._list()
      }
    </section>`;
  }
  private async _import() {
    this._busy = true;
    this._error = "";
    try {
      const result = await this.hass.callWS<{ schedule: ReusableSchedule }>({
        type: "roommind/schedules/import",
        entity_id: this._importEntity,
        fallback_heat: this._importHeat,
        fallback_cool: this._importCool,
      });
      this._begin(result.schedule);
      this._dirty = true;
    } catch (err) {
      this._error = this._message(err);
    } finally {
      this._busy = false;
    }
  }
  private _list() {
    return html`<div class="schedule-grid">
        ${Object.values(this._schedules).map(
          (s) =>
            html`<article>
              <h3>${s.name}</h3>
              <p>
                ${s.area_ids.map((id) => this._roomName(id)).join(", ") || this._t("unassigned")}
              </p>
              <button ?disabled=${this._busy} @click=${() => this._begin(s)}>
                ${this._t("edit_assign")}
              </button>
              <button
                ?disabled=${this._busy}
                @click=${() => {
                  this._begin({
                    ...clone(s),
                    id: "",
                    revision: 0,
                    name: `${s.name} (${this._t("copy")})`,
                    area_ids: [],
                  });
                  this._dirty = true;
                }}
              >
                ${this._t("duplicate")}
              </button>
              <button
                ?disabled=${this._busy || s.area_ids.length > 0}
                title=${this._t("delete_hint")}
                @click=${() => this._delete(s)}
              >
                ${this._t("delete")}
              </button>
            </article>`,
        )}
      </div>
      <div class="actions">
        <button ?disabled=${this._busy} @click=${() => this._begin()}>${this._t("new")}</button>
        ${["Living Room", "Downstairs", "Bedrooms"].filter((name) => !Object.values(this._schedules).some((s) => s.name === name)).map((name) => html`<button ?disabled=${this._busy} @click=${() => this._begin(undefined, name)}>+ ${name}</button>`)}
      </div>
      <details>
        <summary>${this._t("import_title")}</summary>
        <p>${this._t("import_hint")}</p>
        <div class="block">
          <label
            >${this._t("helper")}<select
              .value=${this._importEntity}
              @change=${(e: Event) => {
                this._importEntity = (e.target as HTMLSelectElement).value;
              }}
            >
              <option value="">${this._t("choose_helper")}</option>
              ${Object.entries(this.hass.states)
                .filter(([id]) => id.startsWith("schedule."))
                .map(
                  ([id, entity]) =>
                    html`<option value=${id}>${entity.attributes.friendly_name || id}</option>`,
                )}
            </select></label
          >
          <label
            >${this._t("gap_heat")} (${tempUnit(this.hass)})<input
              type="number"
              step=${tempStep(this.hass)}
              .value=${String(toDisplay(this._importHeat, this.hass))}
              @change=${(e: Event) => {
                this._importHeat = toCelsius(
                  Number((e.target as HTMLInputElement).value),
                  this.hass,
                );
              }}
          /></label>
          <label
            >${this._t("gap_cool")} (${tempUnit(this.hass)})<input
              type="number"
              step=${tempStep(this.hass)}
              .value=${String(toDisplay(this._importCool, this.hass))}
              @change=${(e: Event) => {
                this._importCool = toCelsius(
                  Number((e.target as HTMLInputElement).value),
                  this.hass,
                );
              }}
          /></label>
        </div>
        <button ?disabled=${this._busy || !this._importEntity} @click=${this._import}>
          ${this._t("import_draft")}
        </button>
      </details>`;
  }
  private _editor() {
    const draft = this._draft!;
    const blocks = draft.days[this._day];
    const showCool = this._showCool();
    const unit = tempUnit(this.hass);
    const indoorRooms = Object.entries(this.rooms).filter(([, room]) => !room.is_outdoor);
    return html`<fieldset ?disabled=${this._busy}>
      <label
        >${this._t("name")}<input
          class="name"
          maxlength="80"
          .value=${draft.name}
          @input=${(e: Event) => {
            draft.name = (e.target as HTMLInputElement).value;
            this._change();
          }}
      /></label>
      <div class="days" role="group" aria-label=${this._t("select_day")}>
        ${DAYS.map(
          (day) =>
            html`<button
              class=${this._day === day ? "selected" : ""}
              aria-pressed=${this._day === day}
              @click=${() => {
                this._day = day;
                this._copyDays = DAYS.filter((d) => d !== day);
              }}
            >
              ${this._weekday(day)}
            </button>`,
        )}
      </div>
      <h3>${this._weekday(this._day)}</h3>
      <div class="timeline" aria-label=${this._t("timeline")}>
        ${blocks.map(
          (block, index) => html`
            <div
              class="period"
              style=${`flex:${minutes(block.to) - minutes(block.from)}`}
              title=${`${block.from.slice(0, 5)}–${block.to.slice(0, 5)} · ${toDisplay(block.data.heat_temperature, this.hass)} / ${toDisplay(block.data.cool_temperature, this.hass)}${unit}`}
            >
              <span>${toDisplay(block.data.heat_temperature, this.hass)}${unit}</span>
            </div>
            ${
              index < blocks.length - 1
                ? html`<button
                    class="boundary"
                    style=${`left:${(minutes(block.to) / 1440) * 100}%`}
                    title=${this._t("drag_boundary")}
                    aria-label=${`${this._t("boundary")} ${block.to.slice(0, 5)}`}
                    @pointerdown=${(e: PointerEvent) => this._drag(e, index)}
                    @keydown=${(e: KeyboardEvent) => {
                      if (["ArrowLeft", "ArrowRight"].includes(e.key)) {
                        e.preventDefault();
                        this._boundary(
                          index,
                          minutes(block.to) + (e.key === "ArrowLeft" ? -15 : 15),
                        );
                      }
                    }}
                  ></button>`
                : nothing
            }
          `,
        )}
      </div>
      <div class="axis"><span>00:00</span><span>12:00</span><span>24:00</span></div>
      <p class="hint">${this._t("timeline_hint")}</p>
      ${blocks.map(
        (block, index) =>
          html`<div class="block">
            <label
              >${this._t("from")}<input
                type="time"
                .value=${block.from.slice(0, 5)}
                ?disabled=${index === 0}
                @change=${(e: Event) => this._boundary(index - 1, minutes((e.target as HTMLInputElement).value))}
            /></label>
            <label
              >${this._t("to")}<input
                type=${index === blocks.length - 1 ? "text" : "time"}
                .value=${block.to.slice(0, 5)}
                ?disabled=${index === blocks.length - 1}
                @change=${(e: Event) => this._boundary(index, minutes((e.target as HTMLInputElement).value))}
            /></label>
            <label
              >${this._t("heat_below")} (${unit})<input
                type="number"
                step=${tempStep(this.hass)}
                min=${toDisplay(5, this.hass)}
                max=${toDisplay(35, this.hass)}
                .value=${String(toDisplay(block.data.heat_temperature, this.hass))}
                @change=${(e: Event) => this._temp(index, "heat_temperature", e)}
            /></label>
            ${showCool ? html`<label>${this._t("cool_above")} (${unit})<input type="number" step=${tempStep(this.hass)} min=${toDisplay(5, this.hass)} max=${toDisplay(35, this.hass)} .value=${String(toDisplay(block.data.cool_temperature, this.hass))} @change=${(e: Event) => this._temp(index, "cool_temperature", e)} /></label>` : nothing}
            <div class="actions">
              <button
                ?disabled=${blocks.length >= 48 || minutes(block.to) - minutes(block.from) < 2}
                @click=${() => this._split(index)}
              >
                ${this._t("split")}</button
              ><button ?disabled=${blocks.length === 1} @click=${() => this._remove(index)}>
                ${this._t("remove")}
              </button>
            </div>
          </div>`,
      )}
      ${!showCool ? html`<p class="hint">${this._t("heat_only_hint")}</p>` : nothing}
      <h3>${this._t("copy_day")}</h3>
      <div class="checks">
        ${DAYS.filter((day) => day !== this._day).map(
          (day) =>
            html`<label
              ><input
                type="checkbox"
                .checked=${this._copyDays.includes(day)}
                @change=${(e: Event) => {
                  this._copyDays = (e.target as HTMLInputElement).checked
                    ? [...this._copyDays, day]
                    : this._copyDays.filter((d) => d !== day);
                }}
              />${this._weekday(day)}</label
            >`,
        )}
      </div>
      <button ?disabled=${!this._copyDays.length} @click=${this._copyDay}>
        ${this._t("copy_to_days")}
      </button>
      <h3>${this._t("assign_rooms")}</h3>
      <p class="hint">${this._t("assignment_hint")}</p>
      <div class="checks">
        ${indoorRooms.map(
          ([id, room]) =>
            html`<label
              ><input
                type="checkbox"
                .checked=${draft.area_ids.includes(id)}
                @change=${(e: Event) => {
                  draft.area_ids = (e.target as HTMLInputElement).checked
                    ? [...draft.area_ids, id]
                    : draft.area_ids.filter((a) => a !== id);
                  this._change();
                }}
              />${this._roomName(id)}${room.roommind_schedule_id && room.roommind_schedule_id !== draft.id ? html`<small> (${this._schedules[room.roommind_schedule_id]?.name || this._t("other_schedule")})</small>` : nothing}</label
            >`,
        )}
      </div>
      ${!indoorRooms.length ? html`<p>${this._t("no_rooms")}</p>` : nothing}
      <div class="actions footer">
        <button class="primary" @click=${this._save}>
          ${this._busy ? this._t("saving") : this._t("save")}</button
        ><button
          @click=${() => {
            if (this.canLeave()) {
              this._draft = null;
              this._dirty = false;
              this._error = "";
              void this._load();
            }
          }}
        >
          ${this._t("cancel")}
        </button>
      </div>
    </fieldset>`;
  }
  static styles = css`
    :host {
      display: block;
      font-family: var(--primary-font-family, Roboto, sans-serif);
      color: var(--primary-text-color);
    }
    section {
      max-width: 1000px;
    }
    h2 {
      margin-top: 0;
    }
    p {
      line-height: 1.5;
    }
    .hint,
    small {
      color: var(--secondary-text-color);
      font-size: 13px;
    }
    fieldset {
      border: 0;
      padding: 0;
      min-width: 0;
    }
    label {
      display: flex;
      flex-direction: column;
      gap: 6px;
      font-size: 14px;
    }
    input {
      box-sizing: border-box;
      min-width: 0;
      padding: 10px;
      border: 1px solid var(--divider-color, #888);
      border-radius: 8px;
      background: var(--card-background-color, white);
      color: inherit;
      font: inherit;
    }
    select {
      padding: 10px;
      border-radius: 8px;
      color: inherit;
      background: var(--card-background-color);
      font: inherit;
    }
    details {
      margin-top: 24px;
    }
    summary {
      cursor: pointer;
    }
    input.name {
      max-width: 400px;
    }
    input:disabled {
      opacity: 0.65;
    }
    button {
      cursor: pointer;
      padding: 9px 12px;
      border: 1px solid var(--divider-color, #888);
      border-radius: 8px;
      background: var(--card-background-color, white);
      color: inherit;
      font: inherit;
      min-height: 40px;
    }
    button:disabled {
      opacity: 0.5;
      cursor: default;
    }
    button.selected,
    button.primary {
      background: var(--primary-color, #03a9f4);
      color: var(--text-primary-color, white);
    }
    .days,
    .actions {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      margin: 16px 0;
    }
    .schedule-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 16px;
    }
    article {
      padding: 16px;
      border: 1px solid var(--divider-color, #888);
      border-radius: 12px;
      background: var(--card-background-color);
    }
    article button {
      margin: 4px;
    }
    .timeline {
      display: flex;
      position: relative;
      height: 64px;
      border-radius: 8px;
      background: var(--divider-color);
    }
    .period {
      overflow: hidden;
      display: flex;
      align-items: center;
      justify-content: center;
      background: var(--primary-color, #03a9f4);
      opacity: 0.75;
      min-width: 0;
      color: var(--text-primary-color, white);
    }
    .period:nth-of-type(even) {
      opacity: 1;
    }
    .period span {
      padding: 4px;
      white-space: nowrap;
    }
    button.boundary {
      position: absolute;
      top: -4px;
      bottom: -4px;
      transform: translateX(-50%);
      padding: 0;
      width: 14px;
      min-height: 0;
      background: var(--card-background-color, white);
      border: 2px solid var(--primary-color, #03a9f4);
      cursor: ew-resize;
      touch-action: none;
      z-index: 1;
    }
    .axis {
      display: flex;
      justify-content: space-between;
      font-size: 12px;
      margin-top: 8px;
    }
    .block {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
      gap: 12px;
      padding: 16px 0;
      border-bottom: 1px solid var(--divider-color);
    }
    .block .actions {
      margin: 20px 0 0;
    }
    .checks {
      display: flex;
      flex-wrap: wrap;
      gap: 16px;
      margin: 16px 0;
    }
    .checks label {
      flex-direction: row;
      align-items: center;
    }
    input[type="checkbox"] {
      width: 20px;
      height: 20px;
    }
    .footer {
      position: sticky;
      bottom: 0;
      padding: 16px 0;
      background: var(--primary-background-color);
    }
    .error {
      color: var(--error-color, #db4437);
    }
  `;
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-reusable-schedules": RsReusableSchedules;
  }
}
