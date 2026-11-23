<div class="modal-header"><h2>Wireless</h2></div>
<div class="modal-body update">
<ul class="nav nav-tabs">
<li class="active" id="Wireless_Tab_1"><a href="#" data-remote="modals/wireless-modal.lp?iface=wl0">Telekom 2.4</a></li>
<li id="Wireless_Tab_2"><a href="#" data-remote="modals/wireless-modal.lp?iface=wl0_1&amp;radio=radio_2G">Guest</a></li>
</ul>
<form class="form-horizontal" method="post" action="modals/wireless-modal.lp?iface=wl0">
<fieldset>
<span id="Frequency band">2.4GHz</span>
<div class="control-group"><label class="control-label">State</label><div class="controls"><div class="switch switchOn"><div class="switcher"></div><input type="hidden" name="wifi_state" value="1"></div></div></div>
<div class="control-group"><label class="control-label">Network Name</label><div class="controls"><input type="text" name="ssid" value="Telekom-301213"></div></div>
<div class="control-group"><label class="control-label">Wireless Password</label><div class="controls"><input type="password" name="wpa_psk" value="TOPSECRET123"></div></div>
<div class="control-group"><label class="control-label">Security Key</label><div class="controls"><span class="simple-desc" id="security_key_display">SHOWNSECRET9</span></div></div>
<div class="control-group"><label class="control-label">WPS PIN</label><div class="controls"><input type="text" name="wps_ap_pin" value="12345670"></div></div>
<div class="control-group"><label class="control-label">Security</label><div class="controls"><select name="security"><option value="none">None</option><option value="wpa2-psk" selected>WPA2</option></select></div></div>
<div class="control-group error" style="display:none"><span class="help-inline">Security for this wireless network is disabled</span></div>
<input type="hidden" name="CSRFtoken" value="tok123456789">
</fieldset></form></div>
<div class="modal-footer"><div id="save-config" class="btn btn-primary">Save</div></div>
<script>$("#save-config").click(function(){ var params = {action: "SAVE", fromModal: "YES"}; });</script>
