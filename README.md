# Prisma Configure Mesh
Utility for changing from Hub/Spoke to Partial or Full Mesh for Prisma SD-WAN.

#### Synopsis
Enables simply and flexibly creating Partial, Selective, or Full mesh topologies via a utility.

#### Features
 - Quick one choice Full Mesh or Hub/Spoke config.
 - Detailed Partial/Selective Mesh wizard

#### Requirements
* Active CloudGenix Account
* Python >= 3.7
* Python modules:
    * CloudGenix Python SDK >= 5.5.1b2 - <https://github.com/CloudGenix/sdk-python>
    * Progressbar2 >= 3.53.1 - <https://github.com/WoLpH/python-progressbar>

#### License
MIT

#### Installation:
 - **PIP:** `pip install prisma_configure_mesh`. After install, `prisma_configure_mesh` script should be placed in the Python
 Scripts directory. 
 - **Github:** Download files to a local directory, manually run `prisma_configure_mesh.py` scripts. 

### Examples of usage:
 1. Enable Full Mesh
    ```bash
    edwards-mbp-pro:prisma_configure_mesh aaron$ ./prisma_configure_mesh.py 

    Choose Prisma SD-WAN Network Meshing Stance:
    1: Full Mesh
    2: Partial/Selective Mesh
    3: Hub/Spoke Links Only
    
    Choose a Number or (Q)uit: 1
    
    Checking network state before moving to Full Mesh.
    Loading VPN topology information for 28 sites, please wait.
    100%|##################################################################################################################################################################################|Time:  0:00:03
    
    Changing the Prisma SD-WAN mode to "Full Mesh" will Create:
        341 NEW Public WAN Branch-Branch VPN Mesh Links
        21 NEW Private WAN Branch-Branch VPN Mesh Links
    
    Are you sure? [N]: y
    
    Deploying 362 Branch-Branch VPN Mesh Links..
    100%|##################################################################################################################################################################################|Time:  0:00:41
    
    Prisma SD-WAN Fabric is now in Full Mesh mode.
    edwards-mbp-pro:prisma_configure_mesh aaron$ 
    ```
    
 2. Enable Hub/Spoke mode (Disable Full Mesh)
    ```bash
    edwards-mbp-pro:prisma_configure_mesh aaron$ ./prisma_configure_mesh.py 

    Choose Prisma SD-WAN Network Meshing Stance:
    1: Full Mesh
    2: Partial/Selective Mesh
    3: Hub/Spoke Links Only
    
    Choose a Number or (Q)uit: 3
    
    Checking network state before moving to Hub/Spoke only.
    Loading VPN topology information for 28 sites, please wait.
    100%|##################################################################################################################################################################################|Time:  0:00:04
    
    Changing the Prisma SD-WAN mode to "Hub and Spoke" will Remove:
        341 Public WAN Branch-Branch VPN Mesh Links
        21 Private WAN Branch-Branch VPN Mesh Links
    
    Are you sure? [N]: y
    
    Removing 362 Branch-Branch VPN Mesh Links..
    100%|##################################################################################################################################################################################|Time:  0:00:42
    
    Prisma SD-WAN Fabric is now in Hub/Spoke mode.
    edwards-mbp-pro:prisma_configure_mesh aaron$ 
    ```

 
### Caveats and known issues:
 - *If you have a LARGER network (>500 sites) - Please reach out to support to coordinate enabling full mesh*
    - Selective/Partial mesh is usually the most effective and has the best performance/scale ratio.

#### Version
| Version | Build | Changes |
| ------- | ----- | ------- |
| **1.0.0** | **b1** | Initial Release. 

