#!/usr/bin/env python -u
import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tarfile
import time
import urllib2


def colorize(string, color):
    """Use ANSI escape codes to colorize a string

    Arguments:
    string - string to colorize
    color - one of colorize.colors

    """
    colors = {
        'red': '\033[91m',
        'green': '\033[92m',
        'yellow': '\033[93m',
        'blue': '\033[94m',
        'purple': '\033[95m',
        'white': '\033[97m',

    }
    if not sys.stdout.isatty():
        return string
    return '%s%s%s' % (colors[color], string, '\033[0m')


def pretty_bytes(bytes, precision=2):
    """Nicely format an amount of bytes to use units

    Arguments:
    bytes - number of bytes
    precision - number of decimal points

    Return:
    string of the format: "1.67 MB"

    """
    s = "%%.%sf %%s" % precision
    if bytes == 0:
        return s % (bytes, "B")
    powers = [(2**40, "TB"), (2**30, "GB"), (2**20, "MB"), (2**10, "KB"),
              (1, "B")]
    p = filter(lambda x: bytes >= x[0], powers)[0]
    return s % (float(bytes) / p[0], p[1])


def checksum_file(f, checksum_type="sha256"):
    """Return the hash digest of the file

    Arguments:
    f - file path

    Keyword Arguments:
    checksum_type - one of md5, sha1, sha224, sha256, sha384, sha512

    Return:
    sha256 hext digest string

    """
    hashes = {"md5": hashlib.md5, "sha1": hashlib.sha1,
              "sha224": hashlib.sha224, "sha256": hashlib.sha256,
              "sha384": hashlib.sha384, "sha512": hashlib.sha512}

    if checksum_type not in hashes:
        raise Exception("Unsupported hash type: %s" % checksum_type)

    print "%s %s" % (colorize("Checksuming:", "blue"), f)
    file_name = os.path.basename(f)
    size = os.path.getsize(f)
    h = hashes[checksum_type]()
    block_size = 262144
    input_file = open(f, "rb")
    checked, last_read, rate, time_left = 0, 0, 0.0, 0
    start = time.time()
    while True:
        buf = input_file.read(block_size)
        if not buf:
            break
        checked += len(buf)
        h.update(buf)
        p = float(checked) / float(size)
        end = time.time()
        if end - start > 0.5:
            rate = (checked - last_read) / (end - start)
            last_read = checked
            start = end
            time_left = int((size - checked) / rate)
        # TODO: fix whitespace on the right due to non-overwriting
        print "%s    %05.2f %%    %02.0f:%02.0f:%02.0f    %s/s     \r" % (
            file_name, p * 100.0, time_left / 3600, time_left / 60,
            time_left % 60, pretty_bytes(rate)),
    print ""
    return h.hexdigest()


def download_file(url, output, checksum=None, checksum_type="sha256"):
        """Download a URL from the web

        Arguments:
        url - url to download from
        output - output file

        Keyword Arguments:
        checksum - check downloaded file sha256 againt this

        """
        # Make directory if it doesn't exist
        directory = os.path.dirname(output)
        if not os.path.exists(directory):
            os.makedirs(directory)
        # Download
        file_name = url.split('/')[-1]
        req = urllib2.Request(url)
        u = urllib2.urlopen(req)
        size = int(u.info().getheaders("Content-Length")[0])
        downloaded, last_read, rate, time_left = 0, 0, 0.0, 0
        block_size = 262144
        start = time.time()
        print "%s %s from: %s to %s" % (
            colorize("Downloading:", "blue"),
            colorize(pretty_bytes(size), "green"), url, output)
        if os.path.isfile(output) and os.path.getsize(output) == size:
            print colorize("File size matches. Skipping download.", "yellow")
            if checksum is None:
                return
            else:
                cf = checksum_file(output, checksum_type=checksum_type)
                if cf != checksum:
                    print colorize("Checksum doesn't match redownloading...",
                                   "yellow")
                else:
                    print colorize("Checksum validates. Skipping re-download.",
                                   "yellow")
                    return
        elif os.path.isfile(output) and os.path.getsize(output) < size:
            print colorize("Trying to continue partial download...", "yellow")
            downloaded = os.path.getsize(output)
            last_read = downloaded
            req.headers["Range"] = "bytes=%s-%s" % (downloaded, size - 1)
            u = urllib2.urlopen(req)
            destination = open(output, "ab")
        else:
            destination = open(output, "wb")
        while True:
            buf = u.read(block_size)
            if not buf:
                break
            downloaded += len(buf)
            destination.write(buf)
            p = float(downloaded) / float(size)
            end = time.time()
            if end - start > 0.5:
                rate = (downloaded - last_read) / (end - start)
                last_read = downloaded
                start = end
                time_left = int((size - downloaded) / rate)
            # TODO: fix whitespace on the right due to non-overwriting
            print "%s    %05.2f %%    %02.0f:%02.0f:%02.0f    %s/s     \r" % (
                file_name, p * 100.0, time_left / 3600, time_left / 60,
                time_left % 60, pretty_bytes(rate)),
        print ""
        destination.close()
        if checksum is not None:
            cf = checksum_file(output, checksum_type=checksum_type)
            if cf != checksum:
                print colorize("Checksum didn't validate: %s != %s"
                               "" % (checksum, cf), "red")
                sys.exit(1)


def extract_iso(iso, destination, source=None):
    print "%s %s" % (colorize("Extracting:", "blue"), iso)
    if not os.path.exists(destination):
            os.makedirs(destination)
    # Get a list of all the directories
    p = subprocess.Popen(["isoinfo", "-R", "-l", "-i", iso],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, err = p.communicate()
    last_dir = "/"
    for line in out.split('\n'):
        line = line.rstrip().lstrip()
        if line.startswith("Directory listing of "):
            # Create a new directory
            last_dir = line[len("Directory listing of "):]
            directory = "%s/%s" % (destination, last_dir)
            if not os.path.exists(directory):
                os.makedirs(directory)
        elif line.startswith('d'):
            # Its a nested directory - itll be taken care of later
            pass
        elif len(line) > 0:
            f = "%s%s" % (last_dir, line[line.find("]") + 2:])
            with open("%s/%s" % (destination, f), "w") as output:
                subprocess.call(["isoinfo", "-J", "-i", iso, "-x", f],
                                stdout=output)


class LinuxDistro(object):
    """Abstracts a Linux Distribution
    Expects that fetch, unpack, start, and stop will be subclassed

    dhcp_boot default is pxelinux.0

    """
    def __init__(self, tftp_prefix):
        """Create a new LinuxDistro object

        Arguments:
        tftp_prefix - tftp_root directory name in cwd/root

        """
        super(LinuxDistro, self).__init__()
        self.tftp_root = "%s/root/%s" % (os.getcwd(), tftp_prefix)
        self.dhcp_boot = "pxelinux.0"

    def fetch(self):
        """Download resources from the web
        """
        pass

    def unpack(self):
        """Unpack downloaded resources
        """
        pass

    def start(self):
        """Do anything else before running dnsmasq
        """
        pass

    def stop(self):
        """Do anything else after dnsmasq is stopped
        """
        pass


class RelArchDistro(LinuxDistro):
    """Abstracts a Linux Distribution that has a release and architecture
    Checks that release and architecture are in self.RELEASES

    Expects all subclasses to implement the rest of LinuxDistro

    """

    RELEASES = {}

    def __init__(self, tftp_prefix, release, architecture):
        """Create a new RelArchDistro and check self.RELEASES

        Arguments:
        tftp_prefix - tftp_prefix to pass to LinuxDistro
        release - distribution version
        architecture - machine architecture

        """
        super(RelArchDistro, self).__init__(tftp_prefix)
        self.tftp_root = "%s/%s/%s" % (self.tftp_root, release, architecture)
        self.release = release
        self.architecture = architecture
        # Check that its a valid release
        if self.release not in self.RELEASES:
            raise Exception("No such %s release: %s" % (type(self),
                                                        self.release))
        # Check that the architecture is supported for that release
        if self.architecture not in self.RELEASES[self.release]:
            raise Exception("No architecture %s in release %s" % (
                self.architecture, self.release))


class KernelInitrdDistro(RelArchDistro):
    """Abstracts a RelArchDistro which downloads a kernel and initrd
    The pxelinux configuration is built locally

    Expects a self.RESOURCE_URL which will have three %s placeholders:
    release, architecture, kernel/initrd

    """

    RESOURCE_URL = ""

    RELEASES = {}

    def __init__(self, tftp_prefix, release, architecture, kernel, initrd,
                 k_opts=None, i_opts=None):
        """Create a new KernelInitrdDistro. Ready to download kernel and initrd
        and to configure pxelinux

        Arguments:
        tftp_prefix - tftp_prefix to pass to LinuxDistro
        release - distribution version
        architecture - machine architecture
        kernel - kernel base name
        initrd - initrd base name

        Keyword Arguments:
        k_opts - kernel options to pass at boot
        i_opts - initrd options to pass at boot

        """
        super(KernelInitrdDistro, self).__init__(tftp_prefix, release,
                                                 architecture)
        self.kernel = kernel
        self.initrd = initrd
        self.k_opts = k_opts if k_opts is not None else ""
        self.i_opts = i_opts if i_opts is not None else ""

    def fetch(self):
        download_file(self.RESOURCE_URL % (self.release, self.architecture,
                      self.kernel), "%s/%s" % (self.tftp_root, self.kernel))
        download_file(self.RESOURCE_URL % (self.release, self.architecture,
                      self.initrd), "%s/%s" % (self.tftp_root, self.initrd))

    def unpack(self):
         # Copy syslinux files
        files_to_copy = ["pxelinux.0", "ldlinux.c32", "ldlinux.e32",
                         "ldlinux.e64"]
        for f in files_to_copy:
            print "%s %s" % (colorize("Copying:", "blue"), f)
            shutil.copy("syslinux/%s" % f, self.tftp_root)

        # Write out the menu
        directory = "%s/pxelinux.cfg" % self.tftp_root
        if not os.path.exists(directory):
            os.makedirs(directory)

        kernel_string = """
default linux
label linux
    kernel %s %s
    append initrd=%s %s
                """ % (self.kernel, self.k_opts, self.initrd, self.i_opts)

        print "%s %s" % (colorize("Writing default kernel boot:", "blue"),
                         colorize(kernel_string, "white"))
        with open('%s/default' % directory, 'w') as output:
            output.write(kernel_string)


class ArchLinux(LinuxDistro):
    """docstring for ArchLinux"""
    def __init__(self):
        super(ArchLinux, self).__init__("archlinux")
        self.dhcp_boot = "ipxe.pxe"

    def fetch(self):
        # WARNING: this might easily break since archlinux is rolling...
        download_file("https://releng.archlinux.org/pxeboot/ipxe.pxe",
                      "%s/ipxe.pxe" % self.tftp_root,
                      checksum="2d0c3d05cff23e2382f19c68902554c7388d642e38a9a"
                               "32895db5b890cca4071", checksum_type="sha256")


class CentOS(KernelInitrdDistro):
    """docstring for CentOS"""

    RESOURCE_URL = "http://mirror.centos.org/centos/%s/os/%s/images/pxeboot/%s"

    RELEASES = {
        "5.9": {
            "i386": (None, None),
            "x86_64": (None, None)
        },
        "6.4": {
            "i386": (None, None),
            "x86_64": (None, None)
        }
    }

    def __init__(self, release, architecture):
        super(CentOS, self).__init__(
            "centos", release, architecture, "vmlinuz", "initrd.img",
            k_opts="method=http://mirror.centos.org/centos/%s/os/%s/" % (
                release, architecture), i_opts="devfs=nomount")


class Debian(RelArchDistro):
    """Debian Distribution"""

    RESOURCE_URL = "http://ftp.nl.debian.org/debian/dists/%s/main/" \
                   "installer-%s/current/images/netboot/netboot.tar.gz"

    RELEASES = {
        "squeeze": {
            "amd64": ("ce7278b49b58c3ad48bbe4f4fa921358", "md5"),
            "i386": ("6f32b5b6460eebc81e890bff5127349e", "md5"),
            "ia64": ("cf90be1e05186b3a22808d75e22b2a20", "md5"),
            "kfreebsd-amd64": ("ff05099c9c4ffaa3d8ab234dfb71880e", "md5"),
            "kfreebsd-i386": ("de81fae4e2b818dcaef7870fdf58810c", "md5")
        },
        "wheezy": {
            "amd64": ("f8877de311141263890e751336ab82cf", "md5"),
            "i386": ("99a91a8a9805e82b8713f7355cfbf34f", "md5"),
            "ia64": ("fccf1a31ee08f7e6609ffeb8d91910f2", "md5"),
            "kfreebsd-amd64": ("dc477cc9b3beebd6450e2264ee67580f", "md5"),
            "kfreebsd-i386": ("0bd1d1046b428190d2cced5ddcf63106", "md5")
        }
    }

    def __init__(self, release, architecture):
        """Debian

        Arguments:
        release - release version
        architecture - cpu architecture

        """
        super(Debian, self).__init__("debian", release, architecture)

    def fetch(self):
        checksum, checksum_type = self.RELEASES[self.release][self.architecture]
        download_file(self.RESOURCE_URL % (self.release, self.architecture),
                      "%s/netboot.tar.gz" % self.tftp_root, checksum=checksum,
                      checksum_type=checksum_type)

    def unpack(self):
        # Unpack the downloaded tar file
        print "%s %s/netboot.tar.gz" % (colorize("Unpacking:", "blue"),
                                        self.tftp_root)
        t = tarfile.open('%s/netboot.tar.gz' % self.tftp_root)
        t.extractall(self.tftp_root)


class Fedora(KernelInitrdDistro):
    """docstring for Fedora"""

    RESOURCE_URL = "http://download.fedoraproject.org/pub/fedora/linux" \
                   "/releases/%s/Fedora/%s/os/images/pxeboot/%s"

    RELEASES = {
        "15": {
            "i386": (None, None),
            "x86_64": (None, None)
        },
        "16": {
            "i386": (None, None),
            "x86_64": (None, None)
        },
        "17": {
            "i386": (None, None),
            "x86_64": (None, None)
        },
        "18": {
            "i386": (None, None),
            "x86_64": (None, None)
        },
        "19": {
            "i386": (None, None),
            "x86_64": (None, None)
        },
    }

    def __init__(self, release, architecture):
        super(Fedora, self).__init__(
            "fedora", release, architecture, "vmlinuz", "initrd.img",
            k_opts="inst.repo=http://download.fedoraproject.org/pub/fedora"
                    "/linux/releases/%s/Fedora/%s/os/" % (release,
                                                          architecture))


class OpenSUSE(KernelInitrdDistro):
    """docstring for OpenSUSE"""

    RESOURCE_URL = "http://download.opensuse.org/distribution/%s/repo/oss" \
                   "/boot/%s/loader/%s"

    RELEASES = {
        "11.4": {
            "i386": (None, None),
            "x86_64": (None, None)
        },
        "12.1": {
            "i386": (None, None),
            "x86_64": (None, None)
        },
        "12.2": {
            "i386": (None, None),
            "x86_64": (None, None)
        },
        "12.3": {
            "i386": (None, None),
            "x86_64": (None, None)
        },
        "openSUSE-current": {
            "i386": (None, None),
            "x86_64": (None, None)
        },
        "openSUSE-stable": {
            "i386": (None, None),
            "x86_64": (None, None)
        }
    }

    def __init__(self, release, architecture):
        super(OpenSUSE, self).__init__(
            "opensuse",release, architecture, "linux", "initrd",
            k_opts="install=http://download.opensuse.org/distribution/%s"
                   "/repo/oss/" % release)


class Ubuntu(Debian):
    """Ubuntu Distribution"""

    RESOURCE_URL = "http://archive.ubuntu.com/ubuntu/dists/%s/main" \
                   "/installer-%s/current/images/netboot/netboot.tar.gz"

    RELEASES = {
        "hardy": {
            "amd64": ("cc8b4c83efc5ff91d5de7a6eb122e71c", "md5"),
            "i386": ("9cd31b43ee622759f1d0afd8f0292d2c", "md5")
        },
        "lucid": {
            "amd64": ("0bfd61ea320aff52a453dc9855516e98342930c5bddb87d2265174c2d040c2c0", "sha256"),
            "i386": ("820b9f1a049c43b0511f830e7b1db1ec6a0e73e1617288bdd6aabac39a797557", "sha256")
        },
        "oneiric": {
            "amd64": ("91710c8f0e66d1d9b700d28499872d7a60a22ebaea6e3705d678daa13b066266", "sha256"),
            "i386": ("433b32988cdde07fdf1477791be65669ebd1359eede40809555c767bdd1aa421", "sha256")
        },
        "precise": {
            "amd64": ("ac7f4fed04baa620ec9a6f746615cc62691bb6c6a2ffa0404d957e9ad64a8956", "sha256"),
            "i386": ("7ecda678385471238bed28b47113d8053b88b54b48b3df05f286f7cb7c20f0bd", "sha256")
        },
        "quantal": {
            "amd64": ("5975d5ba3147b106631cb3106a7e933b87772eb311dd8b3f430f1f058a5df773", "sha256"),
            "i386": ("517bbf6c3ff4fa5ad2b8fcc9c02243353543059e966abbab546a16ccf693fc6b", "sha256")
        },
        "raring": {
            "amd64": ("05265419c9fd12c9bbe4c5efa834df02f3bf72381a2c9443ed2706a705081b38", "sha256"),
            "i386": ("cdfed46d5f8f5cc96166b92a64248da620f8d07e80ca6141db7ebcdbae3fb899", "sha256")
        },
        "saucy": {
            "amd64": ("d310cc8d1fc20b90ed48aa16ad9d40eea6c41f2774389a3a6db78038e4072c65", "sha256"),
            "i386": ("dccb4aed6e38d003567466805f6c1cfa29437326bcb9c9366e8f6fe141e0f0f1", "sha256")
        }
    }

    def __init__(self, *args):
        super(Ubuntu, self).__init__(*args)
        # Fix up tftp_root
        self.tftp_root = self.tftp_root.replace("debian", "ubuntu")


class UbuntuLive(RelArchDistro):
    """docstring for UbuntuLive"""

    RESOURCE_URL = "http://releases.ubuntu.com/%s/ubuntu-%s-%s-%s.iso"

    RELEASE_TO_INT = {"hardy": "8.04.4", "lucid": "10.04.4",
                      "oneiric": "11.10", "precise": "12.04",
                      "quantal": "12.10", "raring": "13.04"}

    RELEASES = {
        "hardy": {
            "amd64": ("95f8e95ad745a2cf0ad956674113897a479f34f9ef3c63d4fb3a525144f32f29", "sha256"),
            "i386": ("dfc9a0a85751b1b54cc7b0ae838668e561ea83ad9f98b146d253f566d7d56a38", "sha256")
        },
        "lucid": {
            "amd64": ("837a6ec168913951bf6371a6df6837217790f4210045c9f991eab641533726fe", "sha256"),
            "i386": ("4c4c982beede1094bcb20f93ccd8f79f63dec35b17d3e4b877d620f9faa47c38", "sha256")
        },
        "oneiric": {
            "amd64": ("462a1311378437b64dc507de7da6cab88528939dccee91940f94ce3e57c1cfab", "sha256"),
            "i386": ("31d5254e83457dfe7b46e6c2553b27b41e6e942122edb2b2ff5c3e9a82ad3256", "sha256")
        },
        "precise": {
            "amd64": ("54574f47b1aef0f9e156afd86aa97cf76df89a957f9b5ab43552a427499ba7cb", "sha256"),
            "i386": ("8d5b84835082e6187504eead904f2672c2a9f3ef4ea5da9ddb6e2d6cf203d485", "sha256")
        },
        "quantal": {
            "amd64": ("256a2cc652ec86ff366907fd7b878e577b631cc6c6533368c615913296069d80", "sha256"),
            "i386": ("d91eee1b74fb81f4235fdaed21e7566bbe8965ec6b7206a122f2025365621ad6", "sha256")
        },
        "raring": {
            "amd64": ("b4b20e0293c2305e83a60c605d39cabf43115794d574c68f1492d49fee0ab3d8", "sha256"),
            "i386": ("fe4c4de422734dccc9d33d0e3990ef3440b7648d5c05acae372d5ffc80ca719d", "sha256")
        }
    }

    def __init__(self, release, architecture, version):
        super(UbuntuLive, self).__init__(release, architecture)
        if version not in ("desktop", "server"):
            raise Exception("Unsupported Ubuntu Live version: %s" % version)
        self.version = version
        self.dhcp_boot = "pxelinux.0"
        self.tftp_root = "%s/root/ubuntu_live/%s/%s/%s" % (os.getcwd(),
                                                           self.release,
                                                           self.version,
                                                           self.architecture)
        self.net_ubuntu = self.tftp_root
        self.nfs_root = "%s/nfsroot" % (self.tftp_root)

    def fetch(self):
        checksum, checksum_type = self.RELEASES[self.release][self.architecture]
        download_file(self.RESOURCE_URL % (self.release,
                                           self.RELEASE_TO_INT[self.release],
                                           self.version,
                                           self.architecture),
                      "%s/ubuntu.iso" % self.tftp_root, checksum=checksum,
                      checksum_type=checksum_type)

    def unpack(self):
        # Extract iso
        extract_iso("%s/ubuntu.iso" % self.tftp_root, self.nfs_root)

        # Copy kernel
        for f in ["vmlinuz", "initrd.lz"]:
            print "%s %s" % (colorize("Copying:", "blue"), f)
            shutil.copy("%s/casper/%s" % (self.nfs_root, f), self.tftp_root)

        # Copy syslinux files
        files_to_copy = ["pxelinux.0"]
        if self.architecture == "i386":
            files_to_copy += ["ldlinux.c32", "ldlinux.e32"]
        else:
            files_to_copy += ["ldlinux.e64"]
        for f in files_to_copy:
            print "%s %s" % (colorize("Copying:", "blue"), f)
            shutil.copy("syslinux/%s" % f, self.tftp_root)

        # Write out the menu
        directory = "%s/pxelinux.cfg" % self.tftp_root
        if not os.path.exists(directory):
            os.makedirs(directory)

        kernel_string = """
default linux
label linux
    kernel vmlinuz boot=casper netboot=nfs nfsroot=10.1.0.1:%s
    append initrd=initrd.lz
                """ % self.nfs_root

        print "%s %s" % (colorize("Writing default kernel boot:", "blue"),
                         colorize(kernel_string, "white"))
        with open('%s/default' % directory, 'w') as output:
            output.write(kernel_string)

    def start(self):
        pass

    def stop(self):
        pass


class DNSMasq(object):
    """docstring for DNSMasq"""
    def __init__(self, tftp_root, dhcp_boot, dhcp_range, interface=None):
        super(DNSMasq, self).__init__()
        self.tftp_root = tftp_root
        self.dhcp_boot = dhcp_boot
        self.dhcp_range = dhcp_range
        self.interface = interface

    def start(self):
        print colorize("Running dnsmasq...", "blue")
        args = ["dnsmasq",
                "--pid-file=%s/dnsmasq.pid" % os.getcwd(),
                "--log-facility=%s/dnsmasq.log" % os.getcwd(),
                "--dhcp-leasefile=%s/dnsmasq.leases" % os.getcwd(),
                "--conf-file=/dev/null",
                "--enable-tftp", "--tftp-root=%s" % self.tftp_root,
                "--dhcp-range=%s" % self.dhcp_range,
                "--dhcp-boot=%s" % self.dhcp_boot]
        if self.interface is not None:
            args = args + ["--interface=%s" % self.interface]
        subprocess.call(args)

    @staticmethod
    def stop():
        print colorize("Stopping dnsmasq...", "blue")
        pid = open('%s/dnsmasq.pid' % os.getcwd()).read().rstrip()
        subprocess.call(["kill", pid])


class NAT(object):
    """docstring for NAT"""
    def __init__(self, external, internal):
        super(NAT, self).__init__()
        self.external = external
        self.internal = internal

    def start(self):
        if sys.platform == 'darwin':
            subprocess.call(["sysctl", "-w", "net.inet.ip.forwarding=1"])
            p = subprocess.Popen(["ifconfig", self.external],
                                 stdout=subprocess.PIPE)
            out, err = p.communicate()
            if p.returncode != 0:
                raise Exception("Failed to get ip for NAT device: %s"
                                "" % self.external)
            ip = filter(lambda x: x.lstrip().rstrip().startswith('inet '),
                        out.split('\n'))[0].split()[1]
            subprocess.call(["/usr/sbin/natd", "-alias_address", ip,
                             "-interface", self.external, "-use_sockets",
                             "-same_ports", "-unregistered_only", "-dynamic",
                             "-clamp_mss"])
            subprocess.call(["ipfw", "add", "divert", "natd", "ip", "from",
                             "any", "to", "any", "via", self.external])
        elif sys.platform.startswith('linux'):
            subprocess.call(["sysctl", "-w", "net.ipv4.ip_forward=1"])
            subprocess.call(["iptables", "-t", "nat", "-A", "POSTROUTING",
                             "-o", self.external, "-j", "MASQUERADE"])
            subprocess.call(["iptables", "-A", "FORWARD", "-i", self.external,
                             "-o", self.internal, "-m", "STATE",
                             "--state", "RELATED,ESTABLISHED", "-j", "ACCEPT"])
            subprocess.call(["iptables", "-A", "FORWARD", "-i", self.internal,
                             "-o", self.external, "-j", "ACCEPT"])

    @staticmethod
    def stop():
        if sys.platform == 'darwin':
            subprocess.call(["sysctl", "-w", "net.inet.ip.forwarding=0"])
            subprocess.call(["killall", "-9", "natd"])
            subprocess.call(["ipfw", "-f", "flush"])
        elif sys.platform.startswith('linux'):
            subprocess.call(["sysctl", "-w", "net.ipv4.ip_forward=0"])
            # TODO: change this to remove
            # subprocess.call(["iptables", "-t", "nat", "-A", "POSTROUTING",
                             # "-o", self.external, "-j", "MASQUERADE"])


class NFS(object):
    """docstring for NFS"""
    def __init__(self, path, export_ip, netmask):
        super(NFS, self).__init__()
        self.path = path
        self.export_ip = export_ip
        self.netmask = netmask
        if sys.platform == 'darwin':
            self.export_string = "%s -maproot=root:wheel -network %s -mask %s  # WheelOfDistros" % (self.path, self.export_ip, self.netmask)
        elif sys.platform.startswith('linux'):
            self.export_string = "%s %s/%s (rw,sync,no_subtree_check)  # WheelOfDistros" % (self.path, self.export_ip, self.netmask)

    def start(self):
        with open("/etc/exports", "a") as exports:
            exports.write("%s\n" % self.export_string)
        if sys.platform == 'darwin':
            # subprocess.call(["nfsd", "enable"])
            subprocess.call(["nfsd", "restart"])
        elif sys.platform.startswith('linux'):
            # shit...now we have to guess what distro we're on
            subprocess.call(["..."])

    @staticmethod
    def stop():
        # WARNING: not the safest thing to do... :/
        # Get all the lines, and remove ours
        lines = open("/etc/exports", "r").readlines()
        lines = filter(lambda x: not x.endswith("# WheelOfDistros\n"), lines)
        # Now write back everything else
        with open("/etc/exports", "w") as exports:
            for line in lines:
                exports.write(line)
        if sys.platform == 'darwin':
            # subprocess.call(["nfsd", "enable"])
            subprocess.call(["nfsd", "stop"])


DistroMapping = {"archlinux": ArchLinux, "centos": CentOS,
                 "opensuse": OpenSUSE, "debian": Debian, "fedora": Fedora,
                 "ubuntu": Ubuntu, "ubuntulive": UbuntuLive}

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Install Linux over netboot")
    subcommands = parser.add_subparsers(help="Commands")

    ###########################################################################
    ############################ Download & Serve #############################
    ###########################################################################
    download = subcommands.add_parser("download")
    download.set_defaults(command="download")

    serve = subcommands.add_parser("serve")
    serve.set_defaults(command="serve")
    # dnsmasq interface
    serve.add_argument("--interface", required=True,
                       help="Interface to serve dhcp and tftp")
    # NAT interface
    serve.add_argument("--nat", required=False, help="Interface for NAT")

    # Add subcommands for each distro to download and serve
    for cmd in (download, serve):
        distros = cmd.add_subparsers(help="Distros")

        ################### ArchLinux ###################
        archlinux = distros.add_parser("archlinux")
        archlinux.set_defaults(distro="archlinux")

        ################### Others ###################
        for x in ("centos", "debian", "fedora", "opensuse", "ubuntu", "ubuntulive"):
            d = distros.add_parser(x)
            dc = DistroMapping[x]
            # Distro release
            d.add_argument("release", choices=dc.RELEASES.keys(),
                           help="Distribution version")
            # Architecture
            d.add_argument("architecture",
                           choices=set.union(*[set(dc.RELEASES[z].keys())
                                               for z in dc.RELEASES]))
            if x == "ubuntulive":
                d.add_argument("--version", required=False,
                               choices=["desktop", "server"],
                               default="desktop")
            d.set_defaults(distro=x)

    ###########################################################################
    ################################### Stop ##################################
    ###########################################################################
    stop = subcommands.add_parser("stop")
    stop.set_defaults(command="stop", distro=None)

    args = parser.parse_args()

    # Check for root
    if args.command in ("serve", "stop") and os.getuid() != 0:
        sys.stderr.write(colorize("Need root priveleges to serve/stop\n",
                                  "red"))
        sys.exit(1)

    if args.distro == 'archlinux':
        linux = DistroMapping[args.distro]()
    elif args.distro in ('centos', 'debian', 'fedora', 'opensuse', 'ubuntu'):
        linux = DistroMapping[args.distro](args.release, args.architecture)
    elif args.distro in ('ubuntulive'):
        linux = DistroMapping[args.distro](args.release, args.architecture,
                                           args.version)

    if args.command == "download":
        linux.fetch()
        linux.unpack()
    elif args.command == "serve":
        if args.nat is not None:
            nat = NAT(args.nat, args.interface)
            nat.start()
        linux.start()
        dnsmasq = DNSMasq(linux.tftp_root, linux.dhcp_boot,
                          "10.1.0.100,10.1.0.200,12h",
                          interface=args.interface)
        dnsmasq.start()
        if args.distro in ("ubuntulive"):
            nfs = NFS(linux.nfs_root, "10.1.0.0", "255.255.255.0")
            nfs.start()
    elif args.command == "stop":
        DNSMasq.stop()
        NAT.stop()
        NFS.stop()
