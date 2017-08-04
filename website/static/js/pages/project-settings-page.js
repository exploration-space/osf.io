'use strict';

var $ = require('jquery');
var bootbox = require('bootbox');
var Raven = require('raven-js');
var ko = require('knockout');

var ProjectSettings = require('js/projectSettings.js');
var InstitutionProjectSettings = require('js/institutionProjectSettings.js');

var $osf = require('js/osfHelpers');
require('css/addonsettings.css');

var ctx = window.contextVars;


// Initialize treebeard grid for notifications
var ProjectNotifications = require('js/notificationsTreebeard.js');
var $notificationsMsg = $('#configureNotificationsMessage');
var notificationsURL = ctx.node.urls.api  + 'subscriptions/';
// Need check because notifications settings don't exist on registration's settings page
if ($('#grid').length) {
    $.ajax({
        url: notificationsURL,
        type: 'GET',
        dataType: 'json'
    }).done(function(response) {
        new ProjectNotifications(response);
    }).fail(function(xhr, status, error) {
        $notificationsMsg.addClass('text-danger');
        $notificationsMsg.text('Could not retrieve notification settings.');
        Raven.captureMessage('Could not GET notification settings.', {
            extra: { url: notificationsURL, status: status, error: error }
        });
    });
}

//Initialize treebeard grid for wiki
var ProjectWiki = require('js/wikiSettingsTreebeard.js');
var wikiSettingsURL = ctx.node.urls.api  + 'wiki/settings/';
var $wikiMsg = $('#configureWikiMessage');

if ($('#wgrid').length) {
    $.ajax({
        url: wikiSettingsURL,
        type: 'GET',
        dataType: 'json'
    }).done(function(response) {
        new ProjectWiki(response);
    }).fail(function(xhr, status, error) {
        $wikiMsg.addClass('text-danger');
        $wikiMsg.text('Could not retrieve wiki settings.');
        Raven.captureMessage('Could not GET wiki settings.', {
            extra: { url: wikiSettingsURL, status: status, error: error }
        });
    });
}

$(document).ready(function() {
    // Apply KO bindings for Project Settings
    if ($('#institutionSettings').length) {
        new InstitutionProjectSettings.InstitutionProjectSettings('#institutionSettings', window.contextVars);
    }
    var categoryOptions = [];
    var keys = Object.keys(window.contextVars.nodeCategories);
    for (var i = 0; i < keys.length; i++) {
        categoryOptions.push({
            label: window.contextVars.nodeCategories[keys[i]],
            value: keys[i]
        });
    }
    // need check because node category doesn't exist for registrations
    if ($('#projectSettings').length) {
        var projectSettingsVM = new ProjectSettings.ProjectSettings( {
            currentTitle: ctx.node.title,
            currentDescription: ctx.node.description,
            category: ctx.node.category,
            categoryOptions: categoryOptions,
            node_id: ctx.node.id,
            updateUrl:  $osf.apiV2Url('nodes/' + ctx.node.id + '/'),
        });
        ko.applyBindings(projectSettingsVM, $('#projectSettings')[0]);
    }

    $('#deleteNode').on('click', function() {
        if(ctx.node.childExists){
            $osf.growl('Error', 'Any child components must be deleted prior to deleting this project.','danger', 30000);
        }else{
            ProjectSettings.getConfirmationCode(ctx.node.nodeType, ctx.node.isPreprint);
        }
    });

    // TODO: Knockout-ify me
    $('#commentSettings').on('submit', function() {
        var $commentMsg = $('#configureCommentingMessage');

        var $this = $(this);
        var commentLevel = $this.find('input[name="commentLevel"]:checked').val();

        $osf.postJSON(
            ctx.node.urls.api + 'settings/comments/',
            {commentLevel: commentLevel}
        ).done(function() {
            $commentMsg.text('Successfully updated settings.');
            $commentMsg.addClass('text-success');
            if($osf.isSafari()){
                //Safari can't update jquery style change before reloading. So delay is applied here
                setTimeout(function(){window.location.reload();}, 100);
            } else {
                window.location.reload();
            }

        }).fail(function() {
            bootbox.alert({
                message: 'Could not set commenting configuration. Please try again.',
                buttons:{
                    ok:{
                        label:'Close',
                        className:'btn-default'
                    }
                }
            });
        });

        return false;

    });
    
    /* Before closing the page, Check whether the newly checked addon are updated or not */
    $(window).on('beforeunload',function() {
      //new checked items but not updated
      var checked = uncheckedOnLoad.filter('#selectAddonsForm input:checked');
      //new unchecked items but not updated
      var unchecked = checkedOnLoad.filter('#selectAddonsForm input:not(:checked)');

      if(unchecked.length > 0 || checked.length > 0) {
          return 'The changes on addon setting are not submitted!';
      }

        if (projectSettingsVM) {
            /* Before closing the page, check whether changes made to category, title or
               description are updated or not */
            if (projectSettingsVM.title() !== projectSettingsVM.titlePlaceholder ||
                projectSettingsVM.description() !== projectSettingsVM.descriptionPlaceholder ||
                projectSettingsVM.selectedCategory() !== projectSettingsVM.categoryPlaceholder) {
                return 'There are unsaved changes in your project settings.';
            }
        }
    });
});

var WikiSettingsViewModel = {
    enabled: ko.observable(ctx.wiki.isEnabled), // <- this would get set in the mako template, as usual
    wikiMessage: ko.observable('')
};

WikiSettingsViewModel.enabled.subscribe(function(newValue) {
    var self = this;
    $osf.postJSON(ctx.node.urls.api + 'settings/addons/', {wiki: newValue}
    ).done(function(response) {
        if (newValue) {
            self.wikiMessage('Wiki Enabled');
        }
        else {
            self.wikiMessage('Wiki Disabled');
        }
        //Give user time to see message before reload.
        setTimeout(function(){window.location.reload();}, 1500);
    }).fail(function(xhr, status, error) {
        $osf.growl('Error', 'Unable to update wiki');
        Raven.captureMessage('Could not update wiki.', {
            extra: {
                url: ctx.node.urls.api + 'settings/addons/', status: status, error: error
            }
        });
        setTimeout(function(){window.location.reload();}, 1500);
    });
    return true;
}, WikiSettingsViewModel);

if ($('#selectWikiForm').length) {
    $osf.applyBindings(WikiSettingsViewModel, '#selectWikiForm');
}
