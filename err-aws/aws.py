from errbot import BotPlugin, botcmd
from optparse import OptionParser

from libcloud.compute.types import Provider, NodeState
from libcloud.compute.providers import get_driver
from libcloud.compute.base import NodeImage
from libcloud.compute.drivers.ec2 import EC2SubnetAssociation

import time
import logging
logging.basicConfig(level=logging.DEBUG)

class AWS(BotPlugin):

    def get_configuration_template(self):
        """ configuration entries """
        config = {
            'access_id': None,
            'secret_key': None,
            'ami': None,
            'keypair': None,
            'subnet_id': None,
            'route_table_id': None,
            'volume_size': 1,
            'instance_type': None,
            'datacenter': None,
            'puppet': False,
        }
        return config


    def _connect(self):
        """ connection to aws """
        access_id = self.config['access_id']
        secret_key = self.config['secret_key']
        datacenter = self.config['datacenter']

        cls = get_driver(datacenter)
        driver = cls(access_id, secret_key)
        return driver

    def _find_instance_by_name(self, name):
        driver = self._connect()
        for instance in driver.list_nodes():
            if instance.name == name:
                return instance
                
    def _find_instance_by_id(self, id):
        driver = self._connect()
        for instance in driver.list_nodes():
            if instance.id == id:
                return instance

    def _basic_instance_details(self, name):
        instance = self._find_instance_by_name(name)

        if instance is not None:
            details = {
                'id': instance.id,
                'status': NodeState.tostring(instance.state),
                'ip-private': instance.private_ips,
                'ip-public': instance.public_ips,
                'security_groups': instance.extra['groups'],
                'keypair': instance.extra['key_name'],
            }
        else:
            details = {'error': 'instance named {0} not found.'.format(name)}

        return details

    @botcmd(split_args_with=' ')
    def aws_info(self, msg, args):
        ''' get details of a virtual machine
            options: name
        '''
        vmname = args.pop(0)
        details = self._basic_instance_details(vmname)
        self.send(msg.getFrom(), '{0}: {1}'.format(vmname, details), message_type=msg.getType())

    @botcmd
    def aws_reboot(self, msg, args):
        ''' reboot a virtual machine
            options:
                vm (name): name of virtual machine
            example:
            !aws vm_reboot log1
        '''
        vm = self._find_instance_by_name(args)
        result = vm.reboot()
        response = ''
        if result:
            response = 'Successfully sent request to reboot.'
        else:
            response = 'Unable to complete request.'

        self.send(msg.getFrom(), '{0}: {1}'.format(vm.name, response), message_type=msg.getType())


    @botcmd
    def aws_terminate(self, msg, args):
        ''' terminate/destroy a virtual machine
            options:
                vm (name): name of instance
            example:
            !aws vm_terminate log1
        '''
        vm = self._find_instance_by_name(args)
        result = vm.destroy()
        response = ''
        if result:
            response = 'Successfully sent request to terminate instance.'
        else:
            response = 'Unable to complete request.'

        self.send(msg.getFrom(), '{0}: {1}'.format(vm.name, response), message_type=msg.getType())

    @botcmd(split_args_with=' ')
    def aws_create(self, msg, args):
        ''' create a virtual machine from ami template
            options:
                ami (str): template ami to use
                size (int): disk size of instance in GBs
                tags (str): key=val tags
                subnet_id (str): vpc subnet
                route_table_id (str): vpc subnet's routing table
                keypair (str): key pair to use
                instance_type (str): ami instance type
                puppet (bool): run puppet after provisioning
            example:
            !aws create --ami=i-12321 --size=20 --tags="key1=val1,key2=val2" --keypair=my-key --instance_type=t2.medium --puppet app-server1
        '''
        parser = OptionParser()
        parser.add_option("--ami", dest="ami", default=self.config['ami'])
        parser.add_option("--size", dest="size", type='int', default=15)
        parser.add_option("--subnet_id", dest="subnet_id", default=self.config['subnet_id'])
        parser.add_option("--route_table_id", dest="route_table_id", default=self.config['route_table_id'])
        parser.add_option("--instance_type", dest="instance_type", default=self.config['instance_type'])
        parser.add_option("--tags", dest="tags")
        parser.add_option("--keypair", dest="keypair", default=self.config['keypair'])
        parser.add_option("--puppet", action="store_false",
                          dest="puppet", default=self.config['puppet'])

        (t_options, t_args) = parser.parse_args(args)
        options = vars(t_options)

        vmname = t_args.pop(0)

        # setting up requirements
        network = EC2SubnetAssociation(id=options['subnet_id'],
                                       route_table_id=options['route_table_id'],
                                       subnet_id=options['subnet_id'],
                                       main=True)

        block_dev_mappings = [{'VirtualName': None,
                               'Ebs': {
                                    'VolumeSize': options['size'],
                                    'VolumeType': 'standard',
                                    'DeleteOnTermination': 'true'},
                                    'DeviceName': '/dev/sda'}]

        base_tags = {
            'Name': vmname,
            'team': 'systems',
        }


        if options['tags'] is not None:
            for t_tags in options['tags'].split(','):
                base_tags.update(dict([keys.split('=')]))

        driver = self._connect()

        # Setting up ami + instance type
        sizes = driver.list_sizes()
        size = [s for s in sizes if s.id == options['instance_type']][0]
        image = NodeImage(id=options['ami'], name=None, driver=driver)

        # using key-pair and group
        node = driver.create_node(name=vmname, image=image, size=size,
                                  ex_keyname=options['keypair'],
                                  #ex_securitygroup=SECURITY_GROUP_NAMES, # issue for now
                                  ex_subnet=network,
                                  ex_blockdevicemappings=block_dev_mappings,
                                  ex_metadata=base_tags)

        self.send(msg.getFrom(), '{0}: [1/3] Creating instance'.format(vmname), message_type=msg.getType())
        time.sleep(30)
        self.send(msg.getFrom(), '{0}: [2/3] Running post setup'.format(vmname), message_type=msg.getType())

        if options['puppet']:
            # ready for puppet... let's go!
            self.send(msg.getFrom(), '{0}: Running puppet [disabled]'.format(vmname), message_type=msg.getType())

        self.send(msg.getFrom(), '{0}: [3/3] Request completed'.format(vmname), message_type=msg.getType())
        self.send(msg.getFrom(), '{0}: {1}'.format(vmname, self._basic_instance_details(vmname)), message_type=msg.getType())

