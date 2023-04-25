#!/usr/bin/python

# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
from __future__ import (absolute_import, division, print_function)
import json
from ansible_collections.ansible.controller.plugins.module_utils.controller_api import ControllerAPIModule
from ansible.module_utils.basic import AnsibleModule
__metaclass__ = type

from random import randrange
import time


DOCUMENTATION = r'''
---
module: configuration_item

short_description: This module represents a configuration item which can be orchestrated

# If this is part of a collection, you need to use semantic versioning,
# i.e. the version is of the form "2.5.0" and not "2.4".
version_added: "1.0.0"

description: This module represents a configuration item which can be orchestrated

options:
    name:
        description: The name of the configuration item
        required: true
        type: str
    type:
        description: The type of the configuration item
        required: true
        type: str
    state:
        description: absent or present

author:
    - Juerg Ritter (@jritter)
'''

EXAMPLES = r'''
# Deploy 
- name: Deploy test ip address
  jritter.products.configuration_item:
    name: test_ip
    type: ip
    state: present
'''

RETURN = r'''
# These are examples of possible return values, and in general should use other names for return values.
inventory_id:
    description: Inventory ID in AAP/AWX
    type: int
    returned: always
    sample: 42
'''


def run_module():
    # define available arguments/parameters a user can pass to the module
    argument_spec = dict(
        name=dict(type='str', required=True),
        enabled=dict(type='bool', default=True),
        description=dict(),
        variables=dict(type='dict'),
        type=dict(type='str', required=True),
        timeout=dict(type='int', default=300),
        interval=dict(default=2.0, type='float'),
        state=dict(type='str', required=False, default='present',
                   choices=['present', 'absent'])
    )

    # seed the result dict in the object
    # we primarily care about changed and state
    # changed is if this module effectively modified the target
    # state will include any data that you want your module to pass back
    # for consumption, for example, in a subsequent task
    result = dict(
        changed=False,
        inventory_id=''
    )

    # the AnsibleModule object will be our abstraction working with Ansible
    # this includes instantiation, a couple of common attr would be the
    # args/params passed to the execution, as well as if the module

    module = ControllerAPIModule(argument_spec=argument_spec)

    # if the user is working with this module in only check mode we do not
    # want to make any changes to the environment, just return the current
    # state with no modifications
    if module.check_mode:
        module.exit_json(**result)

    name = module.params.get('name')
    enabled = module.params.get('enabled')
    description = module.params.get('description')
    state = module.params.get('state')
    ci_variables = module.params.get('variables')
    ci_type = module.params.get('type')
    interval = module.params.get('interval')
    timeout = module.params.get('timeout')

    # Attempt to look up the related items the user specified (these will fail the module if not found)
    inventory_id = module.resolve_name_to_id(
        'inventories', 'Configuration Items')

    ci = module.get_one('hosts', name_or_id=name, **
                        {'data': {'inventory': inventory_id}})

    variables = {
        'ci_variables': ci_variables,
    }

    ci_fields = {
        'name': name,
        'inventory': inventory_id,
        'enabled': enabled,
        'type': ci_type,
    }

    # In this case, we need to create the CI and run the template to provision it
    if ci is None and state == 'present':
        # Create the CI in AAP with state creating
        variables['ci_state'] = 'deploying'
        ci_fields['variables'] = json.dumps(variables)
        ci = module.create_or_update_if_needed(
            ci, ci_fields, endpoint='hosts', item_type='host', auto_exit=False)

        template_name = "configure_{}".format(ci_type)
        job_template = module.get_one(
            'job_templates', name_or_id=template_name)
        if job_template is None:
            module.fail_json(
                msg="Unable to find job template by name {0}".format(template_name))
        # Call the Configure Template for this CI
        post_data = {
            'wait': True,
            'extra_vars': {
                'ci_name': ci['name'],
            }
        }
        results = module.post_endpoint(
            job_template['related']['launch'], **{'data': post_data})
        # Wait until the job completes
        results = module.wait_on_url(
            url=results['json']['url'], object_name=template_name, object_type='Job', timeout=timeout, interval=interval)

        # Now we can update the ci
        variables['ci_state'] = 'deployed'
        variables['ci_artifacts'] = results['json']['artifacts']

        if 'ansible_host' in results['json']['artifacts'].keys():
            variables['ansible_host'] = results['json']['artifacts']['ansible_host']

        ci_fields['variables'] = json.dumps(variables)
        ci = module.create_or_update_if_needed(
            ci, ci_fields, endpoint='hosts', item_type='host', auto_exit=False)

        module.exit_json(
            **{ 'changed': True,
                'ci_id': ci['id'],
                'ci_name': ci['name'],
                'ci_type': ci['type'],
                'variables': variables,
                'job_id': results['json']['id'],
                'status': results['json']['status'],
               })

    # In this case, we need to rerun the configuration if the variables changed
    if ci is not None and state == 'present':
        if json.loads(ci['variables'])['ci_variables'] == ci_variables:
            module.exit_json(
                **{'changed': False,
                    'ci_id': ci['id'],
                    'ci_name': ci['name'],
                    'ci_type': ci['type'],
                    'variables': variables,
                   })
        else:
            # Create the CI in AAP with state creating
            variables['ci_state'] = 'reconfiguring'
            ci_fields['variables'] = json.dumps(variables)
            ci = module.create_or_update_if_needed(
                ci, ci_fields, endpoint='hosts', item_type='host', auto_exit=False)

            template_name = "configure_{}".format(ci_type)
            job_template = module.get_one(
                'job_templates', name_or_id=template_name)
            if job_template is None:
                module.fail_json(
                    msg="Unable to find job template by name {0}".format(template_name))
            # Call the Configure Template for this CI
            post_data = {
                'wait': True,
                'extra_vars': {
                    'ci_name': ci['name'],
                }
            }
            results = module.post_endpoint(
                job_template['related']['launch'], **{'data': post_data})
            # Wait until the job completes
            results = module.wait_on_url(
                url=results['json']['url'], object_name=template_name, object_type='Job', timeout=timeout, interval=interval)

            # Now we can update the ci
            variables['ci_state'] = 'deployed'
            ci_fields['variables'] = json.dumps(variables)
            ci = module.create_or_update_if_needed(
                ci, ci_fields, endpoint='hosts', item_type='host', auto_exit=False)
            module.exit_json(
                **{'changed': True,
                    'ci_id': ci['id'],
                    'ci_name': ci['name'],
                    'ci_type': ci['type'],
                    'variables': variables,
                    'job_id': results['json']['id'],
                   })

    # In this case, we don't need to do anything
    if ci is None and state == 'absent':
        module.exit_json(
            **{'changed': False})

    # In this case, we need to decommission the CI, and then delete it.
    if ci is not None and state == 'absent':
        # Create the CI in AAP with state creating
        variables['ci_state'] = 'decommissioning'
        ci_fields['variables'] = json.dumps(variables)
        ci = module.create_or_update_if_needed(
            ci, ci_fields, endpoint='hosts', item_type='host', auto_exit=False)

        template_name = "decommission_{}".format(ci_type)
        job_template = module.get_one(
            'job_templates', name_or_id=template_name)
        if job_template is None:
            module.fail_json(
                msg="Unable to find job template by name {0}".format(template_name))
        # Call the Configure Template for this CI
        post_data = {
            'wait': True,
            'extra_vars': {
                'ci_name': ci['name'],
            }
        }
        results = module.post_endpoint(
            job_template['related']['launch'], **{'data': post_data})
        # Wait until the job completes
        results = module.wait_on_url(
            url=results['json']['url'], object_name=template_name, object_type='Job', timeout=timeout, interval=interval)

        # Now we can update the ci
        variables['ci_state'] = 'decommissioned'
        ci_fields['enabled'] = False
        ci_fields['variables'] = json.dumps(variables)
        ci = module.create_or_update_if_needed(
            ci, ci_fields, endpoint='hosts', item_type='host', auto_exit=False)

        # Tower doesn't allow to delete a host while a job against the same invenotry is running
        # We need a more robust solution here.
        #
        #  https://access.redhat.com/solutions/4016031
        #
        # Maybe just disable it and set it to decommissioned instead?
        #module.delete_if_needed(ci, ci_fields, auto_exit=False)

        module.exit_json(
            **{ 'changed': True,
                'ci_id': ci['id'],
                'ci_name': ci['name'],
                'ci_type': ci['type'],
                'variables': variables,
                'job_id': results['json']['id'],
               })

    if description is not None:
        ci_fields['description'] = description
    if variables is not None:
        ci_fields['variables'] = variables

    # in the event of a successful module execution, you will want to
    # simple AnsibleModule.exit_json(), passing the key/value results
    module.exit_json(**result)


def main():
    run_module()


if __name__ == '__main__':
    main()
