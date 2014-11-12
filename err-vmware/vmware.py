import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from errbot import BotPlugin, botcmd
from optparse import OptionParser

from pyVmomi import vim
from pyVim.connect import SmartConnect, Disconnect
import time
import datetime
import random
import vmutils
import logging
logging.basicConfig(level=logging.DEBUG)

class VMware(BotPlugin):

    def get_configuration_template(self):
        """ configuration entries """
        config = {
            'user': None,
            'pass': None,
            'vcenter': None,
            'template': None,
            'resource_pool': None,
            'vm_dnsdomain': None,
            'vm_user': None,
            'vm_pass': None,
            'puppet': False,
        }
        return config


    @botcmd(split_args_with=' ')
    def vmware_migrate(self, msg, args):
        """ vmware migrate <msg> <args> 
        """
        username = self.config['user']
        password = self.config['pass']
        vcenter = self.config['vcenter']
        vmname = args.pop(0)

        try:
            hostname = args.pop(0)
        except IndexError:
            hostname = None

        try:
            si = SmartConnect(host=vcenter, user=username, pwd=password, port=443)
        except:
            err_text = 'Error connecting to {0}'.format(vcenter)
            logging.info(err_text)
            return err_text

        if hostname:
            try:
                host = vmutils.get_host_by_name(si, hostname)
                hostname = host.name
            except:
                return '{0} not found'.format(hostname)
        else:
            # hostname was not passed
            all_hosts = vmutils.get_hosts(si)
            host = vmutils.get_host_by_name(si, random.choice(all_hosts.values()))
            hostname = host.name

        # Finding source VM
        try:
            vm = vmutils.get_vm_by_name(si, vmname)
        except:
            return '{0} not found.'.format(vmname)

        # relocate spec, to migrate to another host
        # this can do other things, like storage and resource pool
        # migrations
        relocate_spec = vim.vm.RelocateSpec(host=host)

        # does the actual migration to host
        vm.Relocate(relocate_spec)
        Disconnect(si)
        return 'Migrating {0} to {1}'.format(vmname, hostname)

    @botcmd
    def vmware_reboot_vm(self, msg, args):
        ''' reboot a virtual machine
            options:
                vm (name): name of virtual machine
            example:
            !vmware log1
        '''
        username = self.config['user']
        password = self.config['pass']
        vcenter = self.config['vcenter']

        try:
            si = SmartConnect(host=vcenter, user=username, pwd=password, port=443)
        except:
            err_text = 'Error connecting to {0}'.format(vcenter)
            logging.info(err_text)
            return err_text

        # Finding source VM
        try:
            vm = vmutils.get_vm_by_name(si, vmname)
        except:
            return '{0} not found.'.format(vmname)

        try:
            vm.RebootGuest()
        except:
            vm.ResetVM_Task()

        Disconnect(si)
        return 'Rebooting {0}'.format(vmname)


    @botcmd
    def vmware_reboot_host(self, msg, args):
        ''' reboot an esx host
            options:
                host (name): name of esx host
            example:
            !vmware esx1
        '''
        return '[feature disabled]'

    @botcmd(split_args_with=' ')
    def vmware_clone(self, msg, args):
        ''' create a cloned vm from a template
            options:
                cpu (int): number of cpus
                mem (int): amount of RAM in MB
                tmpl (str): template name to use
                pool (str): allocate clone to resource pool
                dnsdomain (str): dns suffix of vm
                vcenter (str): vcenter server
                puppet (bool): run puppet after provisioning
            example:
            !vmware clone --cpu=2 --mem=2048 --pool=DEV --dnsdomain=example.com --puppet app-server1
        '''
        parser = OptionParser()
        parser.add_option("--cpu", dest="cpu", default=1)
        parser.add_option("--mem", dest="mem", default=1024)
        parser.add_option("--tmpl", dest="tmpl", default=self.config['template'])
        parser.add_option("--pool", dest="pool", default=self.config['resource_pool'])
        parser.add_option("--dnsdomain", dest="dnsdomain", default=self.config['vm_dnsdomain'])
        parser.add_option("--vcenter", dest="vcenter", default=self.config['vcenter'])
        parser.add_option("--puppet", action="store_false",
                          dest="puppet", default=self.config['puppet'])

        #(options, t_args) = parser.parse_args(args.split(' '))
        (options, t_args) = parser.parse_args(args)
        data = vars(options)

        username = self.config['user']
        password = self.config['pass']
        vm_username = self.config['vm_user']
        vm_password = self.config['vm_pass']
        vmname = t_args.pop(0)

        try:
            si = SmartConnect(host=data['vcenter'], user=username, pwd=password, port=443)
        except IOError, e:
            err_text = 'Error connecting to {0}'.format(data['vcenter'])
            logging.info(err_text)
            yield err_text
            return

        if vmutils.get_vm_by_name(si, vmname):
            yield 'VM "{0}" already exists.'.format(vmname)
            return

        # Finding source VM
        template_vm = vmutils.get_vm_by_name(si, data['tmpl'])

        # mem / cpu
        vmconf = vim.vm.ConfigSpec(numCPUs=data['cpu'], memoryMB=data['mem'],
                                   annotation='Created by {0} on {1}'.format(msg.getFrom(), str(datetime.datetime.now())))

        # Network adapter settings
        adaptermap = vim.vm.customization.AdapterMapping()
        adaptermap.adapter = vim.vm.customization.IPSettings(ip=vim.vm.customization.DhcpIpGenerator(),
                                                             dnsDomain=data['dnsdomain'])

        # IP
        globalip = vim.vm.customization.GlobalIPSettings()

        # Hostname settings
        ident = vim.vm.customization.LinuxPrep(domain=data['dnsdomain'],
                                               hostName=vim.vm.customization.FixedName(name=vmname))

        # Putting all these pieces together in a custom spec
        customspec = vim.vm.customization.Specification(nicSettingMap=[adaptermap],
                                                        globalIPSettings=globalip,
                                                        identity=ident)

        # Creating relocate spec and clone spec
        resource_pool = vmutils.get_resource_pool(si, data['pool'])
        relocateSpec = vim.vm.RelocateSpec(pool=resource_pool)
        cloneSpec = vim.vm.CloneSpec(powerOn=True, template=False,
                                     location=relocateSpec,
                                     customization=customspec,
                                     config=vmconf)

        # Creating clone task
        clone = template_vm.Clone(name=vmname,
                                  folder=template_vm.parent,
                                  spec=cloneSpec)

        self.send(msg.getFrom(), '{0}: [1/3] Cloning'.format(vmname), message_type=msg.getType())

        # Checking clone progress
        time.sleep(5)
        while True:
            progress = clone.info.progress
            if progress == None:
                break
            time.sleep(2)

        # let's get clone vm info
        vm_clone = vmutils.get_vm_by_name(si, vmname)

        # waiting for new vm to bootup
        vmutils.is_ready(vm_clone)

        # Credentials used to login to the guest system
        creds = vmutils.login_in_guest(username=vm_username, password=vm_password)

        self.send(msg.getFrom(), '{0}: [2/3] Running post setup'.format(vmname), message_type=msg.getType())
        pid = vmutils.start_process(si=si, vm=vm_clone, auth=creds, program_path='/bin/sed', args='-i "/^HOST/s:$:.{0}:" /etc/sysconfig/network'.format(data['dnsdomain']))
        #pid = vmutils.start_process(si=si, vm=vm_clone, auth=creds, program_path='/bin/sed', args='-i "/^127.0.1.1/d" /etc/hosts')
        pid = vmutils.start_process(si=si, vm=vm_clone, auth=creds, program_path='/sbin/reboot', args='')

        # get new vm instance
        time.sleep(15)
        vmutils.is_ready(vm_clone)

        if data['puppet']:
            # ready for puppet... let's go!
            pid = vmutils.start_process(si=si, vm=vm_clone, auth=creds, program_path='/bin/echo', args='$(A=$(facter ipaddress); B=$(facter hostname); C=${B}.{0}; echo $A $C $B >> /etc/hosts)'.format(data['dnsdomain']))
            pid = vmutils.start_process(si=si, vm=vm_clone, auth=creds, program_path='/usr/bin/puppet', args='agent --test')

        self.send(msg.getFrom(), '{0}: [3/3] Request completed'.format(vmname), message_type=msg.getType())

