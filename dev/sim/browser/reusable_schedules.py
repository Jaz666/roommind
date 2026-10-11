"""Browser checks for the built panel. Requires Playwright and system Chromium."""

from pathlib import Path

from playwright.sync_api import sync_playwright

bundle = (Path(__file__).resolve().parents[3] / "custom_components/roommind/frontend/roommind-panel.js").read_text()
with sync_playwright() as pw:
    browser = pw.chromium.launch(executable_path="/usr/bin/chromium", args=["--no-sandbox"])
    for width in [390, 1200]:
        page = browser.new_page(viewport={"width": width, "height": 1000})
        errors = []
        page.on("pageerror", lambda e, page_errors=errors: page_errors.append(str(e)))
        page.route(
            "http://roommind.test/**",
            lambda route: route.fulfill(
                content_type="text/javascript" if route.request.url.endswith(".js") else "text/html",
                body=bundle
                if route.request.url.endswith(".js")
                else '<html><body style="--primary-text-color:#222;--card-background-color:#fff;--primary-background-color:#f7f7f7;--divider-color:#aaa;--primary-color:#0288d1;--secondary-text-color:#555"><script type="module" src="/panel.js"></script></body></html>',
            ),
        )
        page.goto("http://roommind.test/")
        page.wait_for_function("!!customElements.get('rs-reusable-schedules')")
        results = page.evaluate("""async () => {
   const results=[],library={},calls=[];
   const rooms={bedroom:{area_id:'bedroom',climate_mode:'auto',acs:['climate.ac'],devices:[{type:'ac',entity_id:'climate.ac'}],schedules:[],live:{}},guest:{area_id:'guest',climate_mode:'heat_only',acs:[],devices:[{type:'trv',entity_id:'climate.trv'}],schedules:[],live:{}}};
   const hass={language:'en',states:{'schedule.bedroom':{state:'on',attributes:{friendly_name:'Existing bedrooms'}}},areas:{bedroom:{name:'Master Bedroom'},guest:{name:'Guest Room'}},entities:{},devices:{},config:{unit_system:{temperature:'°C'},time_zone:'Europe/London'},callWS:async msg=>{
    calls.push(structuredClone(msg));
    if(msg.type==='roommind/schedules/list') return {schedules:structuredClone(library)};
    if(msg.type==='roommind/schedules/save') {
     const id=msg.schedule_id||'bedrooms';
     library[id]={id,revision:msg.revision+1,name:msg.name,days:structuredClone(msg.days),area_ids:[...msg.area_ids]};
     for(const [rid,room] of Object.entries(rooms)) if(msg.area_ids.includes(rid)) room.roommind_schedule_id=id;else if(room.roommind_schedule_id===id)room.roommind_schedule_id='';
     return {schedule:library[id]};
    }
    if(msg.type==='roommind/rooms/save') {rooms[msg.area_id].roommind_schedule_id=msg.roommind_schedule_id;return {};}
    if(msg.type==='roommind/override/set') return {success:true};
    if(msg.type==='roommind/schedules/import')return {schedule:{...structuredClone(library.bedrooms),id:'',revision:0,name:'Imported helper',area_ids:[]}};
    throw Error('Unexpected API '+msg.type);
   }};
   const editor=document.createElement('rs-reusable-schedules');editor.hass=hass;editor.rooms=rooms;document.body.append(editor);
   const settle=async el=>{await new Promise(r=>setTimeout(r,0));await el.updateComplete;};
   await settle(editor);
   const button=(el,text)=>[...el.shadowRoot.querySelectorAll('button')].find(b=>b.textContent.trim()===text);
   const change=(input,value)=>{input.value=value;input.dispatchEvent(new Event('change'));};
   button(editor,'+ Bedrooms').click();await settle(editor);
   if(editor.shadowRoot.querySelectorAll('.block').length!==3)throw Error('Starter periods missing');
   if(calls.some(c=>c.type==='roommind/schedules/save'))throw Error('Draft saved without click');
   results.push('Bedroom starter is an unsaved full-day draft');
   const nums=()=>editor.shadowRoot.querySelectorAll('.block input[type=number]');
   change(nums()[0],'40');await settle(editor);button(editor,'Save schedule and assignments').click();await settle(editor);
   if(calls.some(c=>c.type==='roommind/schedules/save'))throw Error('Invalid input silently saved');
   change(nums()[0],'18.5');await settle(editor);
   const end=editor.shadowRoot.querySelectorAll('.block input[type=time]')[1];change(end,'06:30');await settle(editor);
   if(editor.shadowRoot.querySelectorAll('.block input[type=time]')[2].value!=='06:30')throw Error('Boundary gap');
   const boundary=editor.shadowRoot.querySelector('.boundary');boundary.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowRight'}));await settle(editor);
   if(editor.shadowRoot.querySelectorAll('.block input[type=time]')[1].value!=='06:45')throw Error('Keyboard boundary failed');
   const rect=editor.shadowRoot.querySelector('.timeline').getBoundingClientRect();
   editor.shadowRoot.querySelector('.boundary').dispatchEvent(new PointerEvent('pointerdown',{clientX:rect.left+rect.width*405/1440}));
   window.dispatchEvent(new PointerEvent('pointermove',{clientX:rect.left+rect.width*420/1440}));window.dispatchEvent(new PointerEvent('pointerup'));await settle(editor);
   if(editor.shadowRoot.querySelectorAll('.block input[type=time]')[1].value!=='07:00')throw Error('Pointer dragging failed');

   button(editor,'Split').click();await settle(editor);if(editor.shadowRoot.querySelectorAll('.block').length!==4)throw Error('Split failed');
   button(editor,'Remove').click();await settle(editor);if(editor.shadowRoot.querySelectorAll('.block').length!==3)throw Error('Remove failed');
   button(editor,'Copy to selected days').click();await settle(editor);
   const checks=editor.shadowRoot.querySelectorAll('input[type=checkbox]');checks[6].checked=true;checks[6].dispatchEvent(new Event('change'));await settle(editor);
   button(editor,'Save schedule and assignments').click();await settle(editor);
   if(library.bedrooms.area_ids[0]!=='bedroom')throw Error('Room assignment missing');
   for(const day of Object.keys(library.bedrooms.days))if(JSON.stringify(library.bedrooms.days[day])!==JSON.stringify(library.bedrooms.days.monday))throw Error('Day copy missing');
   results.push('Precise times, keyboard boundaries, split/remove, day copying and assignment save');
   if(!button(editor,'Delete').disabled)throw Error('Can delete assigned schedule');
   button(editor,'Duplicate').click();await settle(editor);
   if(editor.shadowRoot.querySelectorAll('input[type=checkbox]')[6].checked)throw Error('Duplicate copied assignments');
   window.confirm=()=>true;button(editor,'Cancel').click();await settle(editor);
   results.push('Duplicate is unassigned; assigned schedule cannot be deleted');
   editor.shadowRoot.querySelector('details').open=true;
   const helper=editor.shadowRoot.querySelector('select');change(helper,'schedule.bedroom');await settle(editor);
   button(editor,'Import as draft').click();await settle(editor);
   if(editor.shadowRoot.querySelector('input.name').value!=='Imported helper')throw Error('Import draft not displayed');
   button(editor,'Cancel').click();await settle(editor);
   results.push('HA helper imports into an unsaved draft');
   const link=document.createElement('rs-schedule-link');link.hass=hass;link.editing=true;link.choices=[{id:'bedrooms',name:'Bedrooms'}];link.config={...rooms.bedroom,roommind_schedule:{id:'bedrooms',name:'Bedrooms',targets:{heat_temperature:19,cool_temperature:19.5},next_change:1791712800}};document.body.append(link);await settle(link);
   if(link.shadowRoot.querySelector('select').value!=='bedrooms')throw Error('Assigned source does not show in selector');
   if(!link.shadowRoot.textContent.includes('Cool above 19.5'))throw Error('Split band missing');
   change(link.shadowRoot.querySelector('select'),'');await settle(link);
   if(rooms.bedroom.roommind_schedule_id!=='')throw Error('HA helper restoration did not save');
   results.push('Room source, split targets, next change and HA helper restoration');
   link.remove();
   const overrides=document.createElement('rs-override-section');overrides.hass=hass;overrides.language='en';overrides.config={...rooms.bedroom,roommind_schedule:{next_change:Date.now()/1000+3600},live:{override_active:false}};document.body.append(overrides);await settle(overrides);
   button(overrides,'Custom').click();await settle(overrides);button(overrides,'Until next schedule change').click();await settle(overrides);
   if(!calls.find(c=>c.type==='roommind/override/set'&&c.until_next_change===true))throw Error('Override missing next-change flag');
   overrides.remove();
   results.push('Override can expire at next scheduled change');
   button(editor,'Edit / assign rooms').click();await settle(editor);
   // Heating-only rooms show one target column.
   const cs=editor.shadowRoot.querySelectorAll('input[type=checkbox]');cs[6].checked=false;cs[6].dispatchEvent(new Event('change'));await settle(editor);
   const gs=editor.shadowRoot.querySelectorAll('input[type=checkbox]');gs[7].checked=true;gs[7].dispatchEvent(new Event('change'));await settle(editor);
   if(editor.shadowRoot.querySelectorAll('.block input[type=number]').length!==3)throw Error('Radiator room still shows cooling');
   results.push('Radiator-only assignments show heating targets only');
   if(document.documentElement.scrollWidth>window.innerWidth)throw Error('Mobile horizontal overflow');
   window.testEditor=editor;
   return results;
  }""")
        print(f"Viewport {width}: " + "; ".join(results))
        assert not errors, errors
        if width == 390:
            page.screenshot(path=str(Path("/tmp") / "roommind-schedule-editor-mobile.png"), full_page=True)
        page.close()
    browser.close()
