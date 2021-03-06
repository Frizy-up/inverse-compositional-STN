import numpy as np
import scipy.linalg
import os,time
import tensorflow as tf

import warp

# load MNIST data
def loadMNIST(fname):
	if not os.path.exists(fname):
		# download and preprocess MNIST dataset
		from tensorflow.examples.tutorials.mnist import input_data
		mnist = input_data.read_data_sets("MNIST_data/",one_hot=True)
		trainData,validData,testData = {},{},{}
		trainData["image"] = mnist.train.images.reshape([-1,28,28]).astype(np.float32)
		validData["image"] = mnist.validation.images.reshape([-1,28,28]).astype(np.float32)
		testData["image"] = mnist.test.images.reshape([-1,28,28]).astype(np.float32)
		trainData["label"] = np.argmax(mnist.train.labels.astype(np.float32),axis=1)
		validData["label"] = np.argmax(mnist.validation.labels.astype(np.float32),axis=1)
		testData["label"] = np.argmax(mnist.test.labels.astype(np.float32),axis=1)
		os.makedirs(os.path.dirname(fname))
		np.savez(fname,train=trainData,valid=validData,test=testData)
		os.system("rm -rf MNIST_data")
	MNIST = np.load(fname)
	trainData = MNIST["train"].item()
	validData = MNIST["valid"].item()
	testData = MNIST["test"].item()
	return trainData,validData,testData

# generate training batch
def genPerturbations(opt):
	with tf.name_scope("genPerturbations"):
		X = np.tile(opt.canon4pts[:,0],[opt.batchSize,1])
		Y = np.tile(opt.canon4pts[:,1],[opt.batchSize,1])
		dX = tf.random_normal([opt.batchSize,4])*opt.pertScale \
			+tf.random_normal([opt.batchSize,1])*opt.transScale
		dY = tf.random_normal([opt.batchSize,4])*opt.pertScale \
			+tf.random_normal([opt.batchSize,1])*opt.transScale
		O = np.zeros([opt.batchSize,4],dtype=np.float32)
		I = np.ones([opt.batchSize,4],dtype=np.float32)
		# fit warp parameters to generated displacements
		if opt.warpType=="homography":
			A = tf.concat([tf.stack([X,Y,I,O,O,O,-X*(X+dX),-Y*(X+dX)],axis=-1),
						   tf.stack([O,O,O,X,Y,I,-X*(Y+dY),-Y*(Y+dY)],axis=-1)],1)
			b = tf.expand_dims(tf.concat([X+dX,Y+dY],1),-1)
			pPert = tf.matrix_solve(A,b)[:,:,0]
			pPert -= tf.to_float([[1,0,0,0,1,0,0,0]])
		else:
			if opt.warpType=="translation":
				J = np.concatenate([np.stack([I,O],axis=-1),
									np.stack([O,I],axis=-1)],axis=1)
			if opt.warpType=="similarity":
				J = np.concatenate([np.stack([X,Y,I,O],axis=-1),
									np.stack([-Y,X,O,I],axis=-1)],axis=1)
			if opt.warpType=="affine":
				J = np.concatenate([np.stack([X,Y,I,O,O,O],axis=-1),
									np.stack([O,O,O,X,Y,I],axis=-1)],axis=1)
			dXY = tf.expand_dims(tf.concat([dX,dY],1),-1)
			pPert = tf.matrix_solve_ls(J,dXY)[:,:,0]
	return pPert

# make training batch
def makeBatch(opt,data,PH):
	N = len(data["image"])
	randIdx = np.random.randint(N,size=[opt.batchSize])
	# put data in placeholders
	[image,label] = PH
	batch = {
		image: data["image"][randIdx],
		label: data["label"][randIdx],
	}
	return batch

# evaluation on test set
def evalTest(opt,sess,data,PH,prediction,imagesEval=[]):
	N = len(data["image"])
	# put data in placeholders
	[image,label] = PH
	batchN = int(np.ceil(N/opt.batchSize))
	warped = [{},{}]
	count = 0
	for b in range(batchN):
		# use some dummy data (0) as batch filler if necessary
		if b!=batchN-1:
			realIdx = np.arange(opt.batchSize*b,opt.batchSize*(b+1))
		else:
			realIdx = np.arange(opt.batchSize*b,N)
		idx = np.zeros([opt.batchSize],dtype=int)
		idx[:len(realIdx)] = realIdx
		batch = {
			image: data["image"][idx],
			label: data["label"][idx],
		}
		evalList = sess.run([prediction]+imagesEval,feed_dict=batch)
		pred = evalList[0]
		count += pred[:len(realIdx)].sum()
		if len(imagesEval)>0:
			imgs = evalList[1:]
			for i in range(len(realIdx)):
				if data["label"][idx[i]] not in warped[0]: warped[0][data["label"][idx[i]]] = []
				if data["label"][idx[i]] not in warped[1]: warped[1][data["label"][idx[i]]] = []
				warped[0][data["label"][idx[i]]].append(imgs[0][i])
				warped[1][data["label"][idx[i]]].append(imgs[1][i])
	accuracy = float(count)/N
	if len(imagesEval)>0:
		mean = [np.array([np.mean(warped[0][l],axis=0) for l in warped[0]]),
				np.array([np.mean(warped[1][l],axis=0) for l in warped[1]])]
		var = [np.array([np.var(warped[0][l],axis=0) for l in warped[0]]),
			   np.array([np.var(warped[1][l],axis=0) for l in warped[1]])]
	else: mean,var = None,None
	return accuracy,mean,var
