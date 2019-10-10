#import datasetdatabase as dsdb
import numpy as np
import pandas as pd

import vtk

from skimage import io as skio
from skimage import measure

from matplotlib.path import Path
from mpl_toolkits import mplot3d
import matplotlib.pyplot as plt
from PIL import Image, ImageDraw

import meshcut

import imageio
import os

from shapely.geometry import MultiPoint
from shapely.geometry import Polygon
from shapely.geometry import Point


def create_csv_from_database():
    """Download nuclear mesh databse with dsdb and save in repo."""
	prod = dsdb.DatasetDatabase(config="~/.config_dsdb.json")
	df = prod.get_dataset(id=304).ds
	df.to_csv("mesh_vtk_files/nucleus_timelapse.csv")
	
	return df


def get_mask_from_mesh(polydata, imsize, dz):
    """Given a polydata mesh, create a binary 3D mask, centered on the mask image center."""

	def get_cell_vert_array(i, polydata):
        """Get vertices of nuclear mesh."""
		cell = polydata.GetCell(i)
		ids = cell.GetPointIds()
		return np.array([ids.GetId(j) for j in range(ids.GetNumberOfIds())])

    # Collect all faces and vertices into arrays and shift vertices to be centered with mask image
	faces = np.array([get_cell_vert_array(i, polydata) for i in range(polydata.GetNumberOfCells())])
	verts = np.array([np.array(polydata.GetPoint(i)) for i in range(polydata.GetNumberOfPoints())])
	verts_shift = verts + imsize/2

	z_list = [zslice[2] for zslice in verts_shift]
	zmin = min(z_list)
	zmax = max(z_list)
	
	def get_zslice(n):
        """Use meshcut to get z slices of mesh, create 2D masks of each slice, and combine slices to get 3D mask."""

		im = Image.fromarray(np.zeros((imsize,imsize), np.uint8).T)

		if zmin < n < zmax:
			cut = meshcut.cross_section(verts_shift, faces, [0,0,n], [0,0,1])
			polygon = cut[0][:, :2] # discard z values, they are all the same

			draw = ImageDraw.Draw(im)
			draw.polygon(polygon.round().astype(np.uint8).flatten().tolist(), fill=255)
		#plt.imshow(im)

		return np.array(im)/255

	full_shape = tuple(get_zslice(z) for z in np.linspace(0, imsize, np.round(imsize/dz)))
	mask = np.dstack(full_shape)

	return mask

	
def get_mean_mask(df, imsize, dz):
    """Given many meshes in df, find the average binary image mask of all meshes."""
	
	def get_mesh(i):
        """Read database to get one mesh as polydata."""
		reader = vtk.vtkPolyDataReader()
        # read in a specific file
		reader.SetFileName('mesh_vtk_files/'+df['CellId'][i]+'.vtk')
		reader.Update()
		# get data out of file
		polydata = reader.GetOutput()
		return polydata

	polydata = get_mesh(0)
	sum_mask = get_mask_from_mesh(polydata, imsize, dz)

	for i in range(df.shape[0]):
		polydata = get_mesh(i)
		sum_mask = np.add(sum_mask, get_mask_from_mesh(polydata, imsize, dz))
		
	mean_mask = np.divide(sum_mask, df.shape[0])

	np.save('mean_nuc_mask', mean_mask)
	return mean_mask
	
	
def get_mean_mesh(mask):
    """Get mesh from mean mask, correcting z coordinates from zslice indexes to spatial values consistent with x/y."""

	def fix_z(verts, dz, imsize):
		nz = np.round(imsize/dz)
		dz = imsize/nz
		for vert in verts:
			vert[2] *= dz
		return verts

	verts, faces, normals, values = measure.marching_cubes_lewiner(mask)
	nverts = verts.shape[0]
	verts = fix_z(verts, 0.05, 200)
	
	return verts, faces
	
    
def get_mean_mesh_from_individual_meshes(df, imsize=200, dz=0.05):
    """Master function, getting mean mesh shape from df of meshes."""
	mask = get_mean_mask(df, imsize, dz)
	verts, faces = get_mean_mesh(mask)
	np.save(verts,'nuc_verts')
	np.save(faces, 'nuc_faces')


def plot_nuc_mask(mask, title, az):
    """Plut mask in stripes on 3D axes."""

	fig = plt.figure()
	ax = plt.axes(projection="3d")
	ax.view_init(azim=az)

	verts, faces, normals, values = measure.marching_cubes_lewiner(mask)
	nverts = verts.shape[0]
	verts = fix_z(verts, 0.05, 200)
	x, y, z = verts.T
	ax.plot_trisurf(x, y, faces, z, lw=0, cmap=plt.cm.Paired)

	plt.tight_layout()
	plt.savefig(title, format='png')
	
	
def make_nuc_video(mask, filename):
    """Generate movie of striped mask rotating around z-axis."""
    
	images = []
	for i in np.linspace(0, 360, 25):
		filename = 'az_'+str(int(i))+'.png'
		plot_nuc_mask(mask, filename, i)
		images.append(imageio.imread(filename))
		os.remove(filename)
	imageio.mimsave(filename+'.gif', images)
