<div class="modal-header"><h2 class="span4">Sharing</h2>
<span id="Refresh_id" class="btn-icon">refresh data</span>
<span id="Hide_Advanced_id" class="btn-icon">hide advanced</span><span id="Show_Advanced_id" class="btn-icon">show advanced</span></div>
<div class="modal-body update"><ul class="nav nav-tabs">
<li class="active"><a id="Content Sharing" href="#" data-remote="/modals/contentsharing-modal.lp">Content Sharing</a></li>
<li><a id="Printer Sharing" href="#" data-remote="/modals/printersharing-modal.lp">Printer Sharing</a></li></ul>
<form class="form-horizontal" method="post" action="modals/contentsharing-modal.lp">
{errors}
<div id="success-msg" class="alert alert-success hide">Changes saved successfully</div>
<fieldset><legend>General status</legend>
<div id="samba-warning-msg" class="alert hide">Toggling Samba support will disable and turn off Samba Filesharing</div>
<div class="control-group"><label class="control-label">Samba</label><div class="controls">
<div class="switch"><div class="switcher{samba_class}"></div><input type="hidden" name="samba" value="{samba}"></div></div></div>
<div id="samba-fileshare-msg" class="alert hide">Please enable Samba to turn on Samba Filesharing</div>
<div class="control-group"><label class="control-label">Samba Filesharing</label><div class="controls">
<div class="switch"><div class="switcher{share_class}"></div><input type="hidden" name="sambaFilesharing" value="{share}"></div></div></div>
<div class="control-group"><label class="control-label">Samba name: </label><div class="controls">
<input type="text" name="sambaName" class="edit-input" value="Technicolor"></div></div>
<div class="control-group"><label class="control-label">Samba workgroup: </label><div class="controls">
<input type="text" name="sambaWorkgroup" value="WORKGROUP"></div></div>
<div class="control-group"><label class="control-label">Samba description: </label><div class="controls">
<input type="text" name="sambaDescription" value="Technicolor Gateway"></div></div>
<div class="control-group"><label class="control-label">Storage Interface</label><div class="controls">
<select name="storageInterface" id="storageInterface"><option value="0" selected="selected">LAN</option><option value="1">LAN/WAN</option></select></div></div>
<div class="control-group"><label class="control-label">Anonymous login</label><div class="controls">
<div class="switch"><div class="switcher switcherOn"></div><input type="hidden" name="diskProtection" value="1"></div></div></div>
<div class="control-group"><label class="control-label">Username: </label><div class="controls">
<input type="text" name="userName" value="shareuser"></div></div>
<div class="control-group"><label class="control-label">Password: </label><div class="controls">
<input type="password" name="passWord" value="SHAREPASS77"></div></div>
<div class="control-group"><label class="control-label">DLNA Enabled</label><div class="controls">
<div class="switch"><div class="switcher{dlna_class}"></div><input type="hidden" name="dlnaEnabled" value="{dlna}"></div></div></div>
<div class="control-group"><label class="control-label">DLNA name: </label><div class="controls">
<input type="text" name="dlnaFriendlyName" value="Technicolor DLNA Server"></div></div>
<div id="reboot-warning-msg" class="alert hide">Toggling USB3.1 support will reboot the Gateway</div>
<div class="control-group"><label class="control-label">USB 3.1 Enabled</label><div class="controls">
<div class="switch"><div class="switcher switcherOn"></div><input type="hidden" name="usb3Enabled" value="1"></div></div></div>
<input type="text" name="csFlag" class="hide" value="0">
</fieldset></form></div>
<div class="modal-footer"><div id="modal-no-change"><div id="close-config" class="btn btn-primary btn-large">Close</div></div>
<div id="modal-changes" class="hide"><div id="cancel-config" class="btn btn-large">Cancel</div>
<div id="save-config" class="btn btn-primary btn-large">Save</div></div></div>
